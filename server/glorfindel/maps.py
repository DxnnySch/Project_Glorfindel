"""Kartenproxy (Heft §5.5): Karte wählen, einzeichnen, triviale Animation, Platzhalterclip + Kartenblatt.

Daten als JSON im Folgenordner. Koordinaten normalisiert (0..1) relativ zur Kartenbildgröße.

Element-Typen:
  marker  {x, y, text}                    – Punkt mit Beschriftung
  label   {x, y, text}                    – freie Beschriftung
  pfeil   {punkte: [[x,y],[x,y]], text}   – Pfeil / Pfad (mehrere Punkte = Pfad, zeichnet sich)
  region  {punkte: [[x,y],...], text}     – Polygon
  kamera  {rect: [x,y,w,h]}               – Kamerarahmen
Jedes Element hat optional `t0` (Einblendzeit in s) und `hinweis` (Freitext für den Schnitt).
Keyframes der Kamera: [{t, rect:[x,y,w,h]}] – dazwischen weiche Interpolation.
"""
from __future__ import annotations

import math
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

Image.MAX_IMAGE_PIXELS = None  # Karten sind teils sehr groß
MAP_EXT = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"}
COLORS = {"marker": (220, 40, 40), "pfeil": (240, 160, 20), "region": (60, 120, 230), "label": (255, 255, 255)}


def list_maps(folder: Path, query: str = "") -> list[dict]:
    q = query.lower().strip()
    out = []
    for f in sorted(Path(folder).rglob("*")):
        if f.suffix.lower() in MAP_EXT and (not q or q in f.name.lower()):
            out.append({"name": f.name, "path": f.as_posix(), "size": f.stat().st_size})
    return out


def thumbnail(path: Path, dst: Path, max_side: int = 400) -> Path:
    if not dst.exists():
        with Image.open(path) as im:
            im.draft("RGB", (max_side * 2, max_side * 2))
            im = im.convert("RGB")
            im.thumbnail((max_side, max_side))
            dst.parent.mkdir(parents=True, exist_ok=True)
            im.save(dst, "JPEG", quality=80)
    return dst


def new_map(map_id: str, image_rel: str, dauer: float = 6.0) -> dict:
    return {"id": map_id, "bild": image_rel, "dauer": dauer, "elemente": [], "kamera": [], "hinweise": ""}


def _font(size: int):
    for name in ("arial.ttf", "DejaVuSans.ttf", "Helvetica.ttc"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _ease(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def _el_color(el: dict) -> tuple[int, int, int]:
    """Farbe eines Elements: eigene `farbe` (#rrggbb) oder Standard je Typ."""
    f = str(el.get("farbe") or "").lstrip("#")
    if len(f) == 6:
        try:
            return int(f[0:2], 16), int(f[2:4], 16), int(f[4:6], 16)
        except ValueError:
            pass
    return COLORS.get(el.get("typ"), (255, 255, 255))


def camera_rect(m: dict, t: float) -> list[float]:
    """Kamerarahmen zur Zeit t: Keyframes weich interpoliert; ohne Keyframes das ganze Bild."""
    kfs = sorted(m.get("kamera", []), key=lambda k: k["t"])
    if not kfs:
        return [0.0, 0.0, 1.0, 1.0]
    if t <= kfs[0]["t"]:
        return list(kfs[0]["rect"])
    for a, b in zip(kfs, kfs[1:]):
        if a["t"] <= t <= b["t"]:
            f = _ease((t - a["t"]) / max(b["t"] - a["t"], 1e-6))
            return [a["rect"][i] + (b["rect"][i] - a["rect"][i]) * f for i in range(4)]
    return list(kfs[-1]["rect"])


def _path_progress(points: list[list[float]], p: float) -> list[tuple[float, float]]:
    """Teilstück eines Pfades bis Anteil p (0..1) für die „zeichnet sich“-Animation."""
    if len(points) < 2 or p >= 1:
        return [tuple(pt) for pt in points]
    lens = [math.dist(a, b) for a, b in zip(points, points[1:])]
    target, out = sum(lens) * p, [tuple(points[0])]
    for (a, b), ln in zip(zip(points, points[1:]), lens):
        if target > ln:
            out.append(tuple(b))
            target -= ln
        else:
            f = target / ln if ln else 0
            out.append((a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f))
            break
    return out


def draw_elements(im: Image.Image, m: dict, t: float | None = None, scale: float = 1.0,
                  view: list[float] | None = None) -> Image.Image:
    """Elemente auf Bild `im` zeichnen. `t=None`: alle (Kartenblatt), sonst Zustand zur Zeit t.
    `view`: sichtbarer Ausschnitt (normalisiert), damit Koordinaten des Vollbilds stimmen."""
    d = ImageDraw.Draw(im, "RGBA")
    W, H = im.size
    vx, vy, vw, vh = view or [0, 0, 1, 1]

    def px(p):
        return ((p[0] - vx) / vw * W, (p[1] - vy) / vh * H)

    f = _font(max(12, int(18 * scale)))
    lw = max(2, int(4 * scale))
    for el in m.get("elemente", []):
        t0 = el.get("t0", 0.0)
        if t is not None and t < t0:
            continue
        alpha = 255 if t is None else int(255 * _ease((t - t0) / 0.4))
        typ, col = el["typ"], _el_color(el)
        if typ == "marker":
            x, y = px((el["x"], el["y"]))
            r = max(6, int(10 * scale))
            d.ellipse([x - r, y - r, x + r, y + r], fill=col + (alpha,), outline=(255, 255, 255, alpha), width=2)
            if el.get("text"):
                d.text((x + r + 4, y - r), el["text"], font=f, fill=(255, 255, 255, alpha), stroke_width=2,
                       stroke_fill=(0, 0, 0, alpha))
        elif typ == "label":
            x, y = px((el["x"], el["y"]))
            d.text((x, y), el.get("text", ""), font=f, fill=(255, 255, 255, alpha), stroke_width=2,
                   stroke_fill=(0, 0, 0, alpha))
        elif typ == "pfeil":
            dur = max(el.get("dauer", 1.5), 0.1)
            prog = 1.0 if t is None else _ease((t - t0) / dur)
            pts = [px(p) for p in _path_progress(el["punkte"], prog)]
            if len(pts) >= 2:
                d.line(pts, fill=col + (255,), width=lw, joint="curve")
                (x0, y0), (x1, y1) = pts[-2], pts[-1]
                ang = math.atan2(y1 - y0, x1 - x0)
                hl = 14 * scale + lw
                for s in (-0.45, 0.45):
                    d.line([(x1, y1), (x1 - hl * math.cos(ang + s), y1 - hl * math.sin(ang + s))],
                           fill=col + (255,), width=lw)
            if el.get("text") and pts:
                d.text((pts[0][0] + 6, pts[0][1] + 6), el["text"], font=f, fill=(255, 255, 255, alpha),
                       stroke_width=2, stroke_fill=(0, 0, 0, alpha))
        elif typ == "region":
            pts = [px(p) for p in el["punkte"]]
            if len(pts) >= 3:
                d.polygon(pts, fill=col + (int(alpha * 0.28),), outline=col + (alpha,), width=lw)
                if el.get("text"):
                    cx, cy = sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
                    d.text((cx, cy), el["text"], font=f, fill=(255, 255, 255, alpha), anchor="mm",
                           stroke_width=2, stroke_fill=(0, 0, 0, alpha))
    return im


def render_sheet(m: dict, image_path: Path, dst: Path, max_side: int = 2000) -> Path:
    """Kartenblatt (PNG oder PDF je nach Endung): Skizze + Hinweise + Elementliste."""
    with Image.open(image_path) as src:
        src.draft("RGB", (max_side, max_side))
        base = src.convert("RGB")
    base.thumbnail((max_side, max_side))
    sketch = draw_elements(base.copy(), m, t=None, scale=base.width / 1600)
    # Kamerarahmen einzeichnen
    d = ImageDraw.Draw(sketch)
    for k in m.get("kamera", []):
        x, y, w, h = k["rect"]
        d.rectangle([x * sketch.width, y * sketch.height, (x + w) * sketch.width, (y + h) * sketch.height],
                    outline=(0, 220, 120), width=max(2, sketch.width // 400))
    notes = [m.get("hinweise", "").strip()] if m.get("hinweise", "").strip() else []
    for el in m.get("elemente", []):
        if el.get("hinweis"):
            notes.append(f"• {el.get('text') or el['typ']}: {el['hinweis']}")
    f = _font(max(14, sketch.width // 70))
    line_h = f.size + 6 if hasattr(f, "size") else 18
    margin = 24
    lines: list[str] = []
    for n in ["Kartenplatzhalter – " + m["id"]] + notes:
        lines += _wrap(n, f, sketch.width - 2 * margin)
    panel_h = margin * 2 + line_h * max(1, len(lines))
    sheet = Image.new("RGB", (sketch.width, sketch.height + panel_h), (30, 30, 30))
    sheet.paste(sketch, (0, 0))
    dd = ImageDraw.Draw(sheet)
    y = sketch.height + margin
    for ln in lines:
        dd.text((margin, y), ln, font=f, fill=(235, 235, 235))
        y += line_h
    dst.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(dst, "PDF" if dst.suffix.lower() == ".pdf" else "PNG")
    return dst


def _wrap(text: str, font, width: int) -> list[str]:
    out: list[str] = []
    for para in text.split("\n"):
        cur = ""
        for w in para.split():
            test = (cur + " " + w).strip()
            if font.getlength(test) <= width or not cur:
                cur = test
            else:
                out.append(cur)
                cur = w
        out.append(cur)
    return out


def render_placeholder_clip(m: dict, image_path: Path, dst: Path, fps: int = 24,
                            size: tuple[int, int] = (1280, 534), on_progress=None) -> Path:
    """Platzhalterclip in Rohschnitt-Länge: Kamerafahrt + Elemente + deutlicher „PLATZHALTER“-Schriftzug."""
    W, H = size[0] // 2 * 2, size[1] // 2 * 2  # yuv420p braucht gerade Maße
    with Image.open(image_path) as src:
        src.draft("RGB", (W * 3, H * 3))
        base = src.convert("RGB")
    base.thumbnail((W * 3, H * 3))
    n = max(1, int(round(m.get("dauer", 6.0) * fps)))
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps),
           "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", str(dst)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    f = _font(max(18, H // 14))
    try:
        for i in range(n):
            if on_progress and i % 6 == 0:
                on_progress(i, n)
            t = i / fps
            x, y, w, h = camera_rect(m, t)
            # Ausschnitt im Seitenverhältnis des Clips halten
            bw, bh = base.size
            cw, ch = max(1, int(w * bw)), max(1, int(h * bh))
            if cw / ch > W / H:
                nh = int(cw * H / W)
                y_c = (y * bh + ch / 2)
                top = int(min(max(0, y_c - nh / 2), max(0, bh - nh)))
                box = (int(x * bw), top, int(x * bw) + cw, top + nh)
            else:
                nw = int(ch * W / H)
                x_c = (x * bw + cw / 2)
                left = int(min(max(0, x_c - nw / 2), max(0, bw - nw)))
                box = (left, int(y * bh), left + nw, int(y * bh) + ch)
            box = (box[0], box[1], min(bw, box[2]), min(bh, box[3]))
            frame = base.crop(box).resize((W, H), Image.BILINEAR)
            vx, vy = box[0] / bw, box[1] / bh
            vw, vh = (box[2] - box[0]) / bw, (box[3] - box[1]) / bh
            draw_elements(frame, m, t=t, scale=W / 1600, view=[vx, vy, vw, vh])
            ImageDraw.Draw(frame).text((W // 2, H - H // 12), "PLATZHALTER – KARTE", font=f, fill=(255, 80, 80),
                                       anchor="mm", stroke_width=2, stroke_fill=(0, 0, 0))
            proc.stdin.write(frame.tobytes())
        proc.stdin.close()
        err = proc.stderr.read().decode(errors="replace")
        if proc.wait() != 0:
            raise RuntimeError(f"Platzhalterclip fehlgeschlagen: {err[-300:]}")
    except BrokenPipeError:
        raise RuntimeError("ffmpeg beendete vorzeitig: " + proc.stderr.read().decode(errors="replace")[-300:])
    return dst
