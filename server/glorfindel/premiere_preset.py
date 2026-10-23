"""Sequenz-Vorgabe (.sqpreset) mit der nötigen Spuranzahl erzeugen.

Die Premiere-API kann keine Spuren hinzufügen, aber `Project.createSequence(name, presetPath)` übernimmt die Spuranzahl aus der
Vorgabe. Wir leiten sie aus der von Adobe mitgelieferten „AVCHD 1080p60“-Vorgabe ab (nur Spuren und Bildrate ändern sich).
"""
from __future__ import annotations

import glob
import re
import sys
from pathlib import Path

TICKS_PER_SECOND = 254_016_000_000
BASE_PRESET = Path("Settings") / "SequencePresets" / "Legacy" / "AVCHD" / "1080p" / "AVCHD 1080p60.sqpreset"


def find_base_preset() -> Path | None:
    """Installierte Adobe-Vorgabe suchen (Windows und macOS, jede Premiere-Version)."""
    patterns = []
    if sys.platform == "win32":
        patterns += [r"C:\Program Files\Adobe\Adobe Premiere Pro *\%s" % BASE_PRESET]
    else:
        patterns += ["/Applications/Adobe Premiere Pro */Adobe Premiere Pro *.app/Contents/%s" % str(BASE_PRESET).replace("Settings", "Settings")]
        patterns += ["/Applications/Adobe Premiere Pro */Adobe Premiere Pro *.app/Contents/Resources/%s" % BASE_PRESET]
    found: list[str] = []
    for pat in patterns:
        found += glob.glob(pat)
    return Path(sorted(found)[-1]) if found else None     # neueste Version


def make_sequence_preset(dst: Path, *, video_tracks: int, audio_tracks: int, fps: float = 60.0, base: Path | None = None) -> Path:
    """Schreibt `dst` (UTF-8 mit BOM wie bei Adobe). Gibt den Pfad zurück."""
    src = base or find_base_preset()
    if src is None or not src.exists():
        raise FileNotFoundError("Adobe-Sequenzvorgabe „AVCHD 1080p60“ nicht gefunden (Premiere Pro installiert?)")
    xml = src.read_text(encoding="utf-8-sig")
    ticks = round(TICKS_PER_SECOND / fps)
    for tag, val in (("InitialNumberOfVideoTracks", video_tracks), ("InitialNumberOfStereoTracks", audio_tracks),
                     ("InitialNumberOfFiveOneTracks", 0), ("VideoFrameRate", ticks)):
        xml, n = re.subn(rf"<{tag}>\d+</{tag}>", f"<{tag}>{val}</{tag}>", xml)
        if n != 1:
            raise ValueError(f"Vorgabe unerwartet: <{tag}> kommt {n}× vor")
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(xml, encoding="utf-8-sig")
    return dst


def read_preset_counts(path: Path) -> dict:
    xml = path.read_text(encoding="utf-8-sig")
    g = lambda t: int(re.search(rf"<{t}>(\d+)</{t}>", xml).group(1))  # noqa: E731
    return {"video": g("InitialNumberOfVideoTracks"), "audio": g("InitialNumberOfStereoTracks"),
            "fps": TICKS_PER_SECOND / g("VideoFrameRate")}
