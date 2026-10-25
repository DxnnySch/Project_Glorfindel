"""Medien für den Premiere-Rohschnitt: konforme Referenz (konstante Bildrate) und Credit-Grafiken.

Wichtig für die Bildgenauigkeit: Die Datei, die in Premiere in der Episoden-Sequenz liegt, ist **dieselbe**, aus der die Standbilder
gezogen werden. Der Bildschirmmitschnitt hat variable Bildrate und Letterbox – Premiere und ffmpeg würden ihn unterschiedlich lesen.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

from . import media

EPISODE_SIZE = (1920, 800)
EPISODE_FPS = 24000 / 1001
FRAME = (1920, 1080)

# Position der Credit-Texte im Originalschnitt (normiert auf die Sequenz 1920×1080, Text-Anker links oben bzw. mittig)
CREDIT_POS = {
    "artwork": (0.5, 0.0833, "mitte"),       # oben mittig über dem Bild
    "amazon": (0.02917, 0.9563, "links"),    # unten links
    "musik": (0.97630, 0.9563, "rechts"),    # unten rechts
}
FONT_CANDIDATES = [
    os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Windows\Fonts\GrandCentral-Light Regular.ttf"),
    r"C:\Windows\Fonts\GrandCentral-Light.ttf", "GrandCentral-Light.otf", "GrandCentral-Light.ttf",
    r"C:\Windows\Fonts\segoeuisl.ttf", "/System/Library/Fonts/Helvetica.ttc", "DejaVuSans.ttf", "arial.ttf",
]


def conform_reference(src: Path, dst: Path, *, crop: list[int] | None = None, fps: float = EPISODE_FPS,
                      size: tuple[int, int] = EPISODE_SIZE, crf: int = 17, on_progress=None) -> Path:
    """Referenz in konstante Bildrate bringen, Letterbox abschneiden, auf Episodengröße bringen. Zeitachse bleibt erhalten."""
    w, h = size
    vf = []
    if crop:
        cx, cy, cw, ch = crop
        vf.append(f"crop={cw}:{ch}:{cx}:{cy}")
    vf += [f"fps={fps:.6f}", f"scale={w}:{h}:force_original_aspect_ratio=decrease:flags=lanczos",
           f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black", "setsar=1", "format=yuv420p"]
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(".part.mp4")
    cmd = [media._bin("ffmpeg"), "-y", "-v", "error", "-i", str(src), "-map", "0:v:0", "-map", "0:a:0?", "-vf", ",".join(vf),
           "-fps_mode", "cfr", "-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf), "-g", "48", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-write_tmcd", "0", "-map_chapters", "-1", "-movflags", "+faststart", str(tmp)]
    try:
        dur = media.probe(src)["duration"]
    except Exception:  # noqa: BLE001
        dur = None
    try:
        r = media.run_ffmpeg(cmd, dur, on_progress)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    if r.returncode != 0:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"Konforme Referenz fehlgeschlagen: {r.stderr.strip()[-300:]}")
    tmp.replace(dst)
    return dst


def _font(px: int):
    from PIL import ImageFont
    for f in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(f, px)
        except OSError:
            continue
    return ImageFont.load_default()


def credit_png(text: str, kind: str, dst_dir: Path, *, font_px: int = 26, x_override: float | None = None) -> Path:
    """Credit als Vollbild-PNG (1920×1080, transparent): weiße Schrift mit weichem Schatten an der Originalposition.
    `x_override`: Mitte des Bildes (0..1) für Doppelbild-Layouts. Dateiname aus Inhalt abgeleitet → Wiederverwendung."""
    from PIL import Image, ImageDraw, ImageFilter
    nx, ny, align = CREDIT_POS.get(kind, CREDIT_POS["artwork"])
    if x_override is not None:
        nx = x_override
    key = hashlib.sha1(f"{text}|{kind}|{nx:.4f}|{font_px}".encode("utf-8")).hexdigest()[:12]
    dst = dst_dir / f"credit_{kind}_{key}.png"
    if dst.exists():
        return dst
    dst_dir.mkdir(parents=True, exist_ok=True)
    W, H = FRAME
    font = _font(font_px)
    probe = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    l, t, r, b = probe.textbbox((0, 0), text, font=font)
    tw, th = r - l, b - t
    x = nx * W
    x = x - tw / 2 if align == "mitte" else x - tw if align == "rechts" else x
    y = ny * H if kind == "artwork" else ny * H - th      # Fußzeilen: Unterkante auf der Originalhöhe
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).text((x - l + 2, y - t + 2), text, font=font, fill=(0, 0, 0, 200))
    shadow = shadow.filter(ImageFilter.GaussianBlur(3))
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(layer).text((x - l, y - t), text, font=font, fill=(255, 255, 255, 255))
    Image.alpha_composite(shadow, layer).save(dst)
    return dst


def play_pause_clips(pause_src: Path, out_dir: Path) -> tuple[Path, Path]:
    """Pause-Animation (Quelle) und daraus rückwärts abgespieltes „Play“ als eigene .mov (ProRes 4444 mit Alpha, einmalig erzeugt)."""
    play = out_dir / "Play.mov"
    out_dir.mkdir(parents=True, exist_ok=True)
    if not play.exists() or play.stat().st_mtime < pause_src.stat().st_mtime:
        tmp = play.with_name("Play.tmp.mov")
        cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(pause_src), "-vf", "reverse", "-an", "-c:v", "prores_ks", "-profile:v", "4444",
               "-pix_fmt", "yuva444p10le", str(tmp)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0 or not tmp.exists():
            raise RuntimeError(f"Play-Animation konnte nicht erzeugt werden: {r.stderr.strip()[-300:]}")
        tmp.replace(play)
    return pause_src, play


def bars_png(dst: Path, *, size: tuple[int, int] = (1920, 1080), fraction: float = 0.13) -> Path:
    """Schwarzstreifen oben und unten (je 13 %, wie „Zuschneiden“ im Ursprungsschnitt), Mitte transparent."""
    from PIL import Image, ImageDraw
    dst.parent.mkdir(parents=True, exist_ok=True)
    w, h = size
    bar = round(h * fraction)
    im = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, w, bar - 1], fill=(0, 0, 0, 255))
    d.rectangle([0, h - bar, w, h], fill=(0, 0, 0, 255))
    im.save(dst)
    return dst
