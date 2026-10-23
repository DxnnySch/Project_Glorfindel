"""Wartung im Hintergrund: ältere Proxys (Stereo-Ton, Datenspuren) einmalig auf das schnelle Format umstellen.

Hintergrund: Stereo-AAC macht Firefox beim Springen in langen Proxys extrem langsam. Das Bild wird nur kopiert,
nur der Ton neu kodiert – das dauert Sekunden bis wenige Minuten je Proxy.
"""
from __future__ import annotations

from pathlib import Path

from . import media
from .config import app_dir
from .progress import as_progress


def old_proxies() -> list[Path]:
    root = app_dir() / "cache"
    out = []
    for f in sorted(root.glob("*/proxy_*.mp4")) if root.is_dir() else []:
        if ".part" in f.name or ".fix" in f.name:
            continue
        try:
            if media.proxy_needs_fix(f):
                out.append(f)
        except Exception:  # noqa: BLE001
            continue
    return out


def fix_old_proxies(progress=None) -> dict:
    pg = as_progress(progress)
    todo = old_proxies()
    if not todo:
        return {"fixed": 0, "skipped": 0}
    pg.plan([(f"{p.parent.name}/{p.name}", max(1, p.stat().st_size // 50_000_000)) for p in todo])
    fixed = skipped = 0
    for i, f in enumerate(todo):
        pg.step(i, f"Ton auf Mono umstellen (Bild wird nur kopiert) – {f.stat().st_size // 1_000_000} MB")
        try:
            media.fix_proxy_audio(f, on_progress=lambda fr, info: pg.fraction(fr, info["text"]))
            fixed += 1
        except PermissionError:
            skipped += 1   # Datei wird gerade abgespielt; beim nächsten Start erneut
        except RuntimeError:
            skipped += 1
    return {"fixed": fixed, "skipped": skipped}
