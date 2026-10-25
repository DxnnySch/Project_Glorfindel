"""Automatischer Bildausschnitt für Artworks: Ein Vision-Modell (ScaDS.AI) markiert das Hauptmotiv, daraus werden Skalierung und Lage des Bildes
hinter der Maske berechnet. Nur die Artwork-Bilder (verkleinert) werden gesendet; ohne Schlüssel/Modell bleibt der Ausschnitt mittig."""
from __future__ import annotations

import base64
import hashlib
import io
import json
from pathlib import Path

from . import store

PROMPT = ("Bestimme auf diesem Bild den Bereich mit dem Hauptmotiv, das in einem Zuschnitt unbedingt sichtbar sein muss "
          "(bei Figuren: Kopf/Gesicht und der markanteste Teil von Körper oder Gegenstand; bei Landschaften/Gebäuden: der auffälligste Teil). "
          "Gib den Bereich als Rahmen in ganzen Zahlen von 0 bis 1000 an (Bildbreite/-höhe = 1000), Ursprung oben links: x0,y0 = linke obere Ecke, x1,y1 = rechte untere Ecke. "
          "Antworte immer und ausschließlich mit JSON der Form {\"x0\":200,\"y0\":100,\"x1\":800,\"y1\":900} – kein weiterer Text.")


def _key(path: Path) -> str:
    st = path.stat()
    return hashlib.sha1(f"{path}|{st.st_size}|{int(st.st_mtime)}".encode()).hexdigest()[:20]


def _data_url(path: Path, max_side: int = 768) -> str:
    from PIL import Image
    with Image.open(path) as im:
        im = im.convert("RGB")
        im.thumbnail((max_side, max_side))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=85)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def _clean(box: dict | None) -> dict | None:
    try:
        x0, y0, x1, y1 = (float(box[k]) for k in ("x0", "y0", "x1", "y1"))
    except (TypeError, KeyError, ValueError):
        return None
    if max(x0, y0, x1, y1) > 1.5:                      # Vision-Modelle liefern 0–1000
        x0, y0, x1, y1 = (v / 1000 for v in (x0, y0, x1, y1))
    x0, x1 = sorted((min(max(x0, 0.0), 1.0), min(max(x1, 0.0), 1.0)))
    y0, y1 = sorted((min(max(y0, 0.0), 1.0), min(max(y1, 0.0), 1.0)))
    if x1 - x0 < 0.05 or y1 - y0 < 0.05:
        return None
    return {"x0": x0, "y0": y0, "x1": x1, "y1": y1}


def subject_box(llm, path: Path, cache_file: Path | None = None) -> dict | None:
    """Rahmen des Hauptmotivs (relativ) oder None. Ergebnisse werden je Bilddatei zwischengespeichert."""
    if llm is None or not llm.enabled("autoframe") or not path.exists():
        return None
    cache = store.read_json(cache_file, {}) if cache_file else {}
    k = _key(path)
    if k in cache:
        return _clean(cache[k])
    model = llm.model_for("autoframe")
    if not model:
        return None
    try:
        r = llm.client.chat.completions.create(model=model, max_tokens=200, temperature=0.0, messages=[
            {"role": "user", "content": [{"type": "text", "text": PROMPT}, {"type": "image_url", "image_url": {"url": _data_url(path)}}]}])
        text = r.choices[0].message.content or ""
        import re
        m = re.search(r"\{.*?\}", text, flags=re.S)
        box = _clean(json.loads(m.group(0))) if m else None
    except Exception as e:  # noqa: BLE001
        llm.last_error = str(e)[:300]
        return None
    if cache_file and box:
        cache[k] = box
        store.write_json(cache_file, cache)
    return box


LANDSCAPE_MIN_RATIO = 1.25          # Breite/Höhe ab hier: Querformat-Maske (Maske.png), sonst abgerundetes Quadrat (Maske Quadrat.png)
VISIBLE_PX = {"Maske.png": (1920, 800), "Maske Quadrat.png": (920, 800)}    # sichtbare Fläche der Masken bei 100 % (Dateien sind 1920×800)
FRAME_PX = (1920, 1080)


def pick_mask(size: tuple[int, int]) -> str:
    w, h = size
    return "Maske.png" if h and w / h >= LANDSCAPE_MIN_RATIO else "Maske Quadrat.png"


def frame_image(size: tuple[int, int], mask: str, shown_w: float, box: dict | None, margin: float = 0.10,
                center: tuple[float, float] = (0.5, 0.5)) -> dict:
    """Ausschnitt eines Artworks hinter der Maske.

    `shown_w`: gewünschte Breite der sichtbaren Maskenfläche auf dem Bildschirm (px bei 1920×1080). Die Maske wird darauf skaliert, das Bild so,
    dass der gewählte Bildausschnitt genau die Fläche füllt (keine leeren Ränder). Der Ausschnitt hat das Seitenverhältnis der Maske, enthält
    das Hauptmotiv samt Rand (wenn das Bild es hergibt) und liegt innerhalb des Bildes. `center`: Mitte der Maske im Rahmen (normiert).
    Rückgabe: mask_scale/image_scale in %, mask_position/image_position normiert (Position des Bildmittelpunkts)."""
    w, h = size
    vw, vh = VISIBLE_PX[mask]
    ar = vw / vh
    mask_scale = shown_w / vw * 100
    # größtmöglicher Ausschnitt im Seitenverhältnis der Maske, der noch ins Bild passt
    max_w = min(w, h * ar)
    bw, bh = ((box["x1"] - box["x0"]) * w, (box["y1"] - box["y0"]) * h) if box else (0.0, 0.0)
    cx, cy = (((box["x0"] + box["x1"]) / 2) * w, ((box["y0"] + box["y1"]) / 2) * h) if box else (w / 2, h / 2)
    # Ausschnitt: so klein wie möglich (Motiv groß), aber das Motiv mit Rand muss hineinpassen; sonst der größtmögliche
    need_w = max(bw * (1 + margin), bh * (1 + margin) * ar)
    rw = min(max(need_w, 0.0), max_w) if box else max_w
    rw = max(rw, min(max_w, w * 0.45))                      # nicht übertrieben nah heranzoomen
    rh = rw / ar
    rx = min(max(cx - rw / 2, 0.0), w - rw)                 # Ausschnitt um das Motiv zentrieren, im Bild halten
    ry = min(max(cy - rh / 2, 0.0), h - rh)
    s = shown_w / rw                                        # Bildpixel → Bildschirmpixel
    ox = center[0] * FRAME_PX[0] + (w / 2 - (rx + rw / 2)) * s    # Bildmitte relativ zur Maskenmitte
    oy = center[1] * FRAME_PX[1] + (h / 2 - (ry + rh / 2)) * s
    return {"mask": mask, "mask_scale": round(mask_scale, 3), "image_scale": round(s * 100, 3),
            "mask_position": [round(center[0], 5), round(center[1], 5)],
            "image_position": [round(ox / FRAME_PX[0], 5), round(oy / FRAME_PX[1], 5)],
            "region": [round(rx / w, 4), round(ry / h, 4), round((rx + rw) / w, 4), round((ry + rh) / h, 4)]}
