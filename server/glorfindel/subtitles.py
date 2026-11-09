"""Untertitel (Amazon liefert SRT, VTT oder TTML/DFXP) als Dialog der Episode: ersetzt die Transkription.

Die Untertitel gehören zu einer Quelldatei (meist der HQ-Datei); ihre Zeiten werden über die Anker dieser
Quelle in Episodenzeit umgerechnet. Pro Untertitel wird die Zeit gleichmäßig nach Buchstaben auf die Wörter verteilt.
"""
from __future__ import annotations

import html
import re
from pathlib import Path

from defusedxml import ElementTree as ET

from .timemap import TimeMap

SUB_EXT = {".srt", ".vtt", ".ttml", ".dfxp", ".xml"}
_TIME = re.compile(r"(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{1,3})")
_TAG = re.compile(r"<[^>]+>|\{\\[^}]*\}")
_SOUND = re.compile(r"^[\[(＜<].*[\])＞>]$|^[♪♫#\s]+$")     # [Musik], (seufzt), ♪ …
LANG_ALIASES = {"deu": "de", "ger": "de", "german": "de", "deutsch": "de", "eng": "en", "english": "en", "englisch": "en"}


def _secs(s: str) -> float:
    m = _TIME.fullmatch(s.strip())
    if not m:
        raise ValueError(s)
    h, mi, se, ms = m.groups()
    return int(h or 0) * 3600 + int(mi) * 60 + int(se) + int(ms.ljust(3, "0")) / 1000


def _clock(v: str, tick_rate: float, frame_rate: float) -> float:
    v = v.strip()
    if v.endswith("t"):                                  # TTML-Ticks
        return float(v[:-1]) / tick_rate
    if v.endswith("ms"):
        return float(v[:-2]) / 1000
    if v.endswith("s"):
        return float(v[:-1])
    p = v.split(":")
    if len(p) == 4:                                      # HH:MM:SS:FF
        return int(p[0]) * 3600 + int(p[1]) * 60 + int(p[2]) + int(p[3]) / frame_rate
    return _secs(v)


def _clean(text: str) -> str:
    text = html.unescape(_TAG.sub("", text))
    lines = [re.sub(r"^\s*[-–—]\s*", "", ln).strip() for ln in re.split(r"[\r\n]+", text)]
    return " ".join(ln for ln in lines if ln and not _SOUND.match(ln))


def parse_text_cues(raw: str) -> list[tuple[float, float, str]]:
    """SRT und WebVTT."""
    cues = []
    for block in re.split(r"\r?\n\r?\n+", raw.replace("﻿", "").strip()):
        lines = block.splitlines()
        for i, ln in enumerate(lines):
            if "-->" in ln:
                a, _, b = ln.partition("-->")
                try:
                    t0, t1 = _secs(a), _secs(b.strip().split()[0])
                except (ValueError, IndexError):
                    break
                text = _clean("\n".join(lines[i + 1:]))
                if text:
                    cues.append((t0, t1, text))
                break
    return cues


def parse_ttml(raw: bytes) -> list[tuple[float, float, str]]:
    root = ET.fromstring(raw)
    attrs = {k.split("}")[-1]: v for k, v in root.attrib.items()}
    tick = float(attrs.get("tickRate", 10_000_000) or 10_000_000)
    fps = float(attrs.get("frameRate", 24) or 24)
    cues = []
    for el in root.iter():
        if el.tag.split("}")[-1] != "p":
            continue
        a = {k.split("}")[-1]: v for k, v in el.attrib.items()}
        if "begin" not in a:
            continue
        try:
            t0 = _clock(a["begin"], tick, fps)
            t1 = _clock(a["end"], tick, fps) if "end" in a else t0 + _clock(a["dur"], tick, fps)
        except (ValueError, KeyError):
            continue
        parts = []
        for node in el.iter():
            if node.tag.split("}")[-1] == "br":
                parts.append("\n")
            if node.text:
                parts.append(node.text)
            if node is not el and node.tail:
                parts.append(node.tail)
        text = _clean("".join(parts))
        if text:
            cues.append((t0, t1, text))
    return cues


def parse_file(path: Path) -> list[tuple[float, float, str]]:
    data = path.read_bytes()
    head = data[:400].lstrip(b"\xef\xbb\xbf").lstrip()
    if head.startswith(b"<"):
        return parse_ttml(data)
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return parse_text_cues(data.decode(enc))
        except UnicodeDecodeError:
            continue
    return []


def cues_to_words(cues: list[tuple[float, float, str]], tm: TimeMap | None = None) -> list[dict]:
    """Wortliste {w,start,end} in Episodenzeit; Zeit je Untertitel anteilig nach Buchstaben verteilt."""
    words: list[dict] = []
    for t0, t1, text in sorted(cues):
        toks = text.split()
        if not toks or t1 <= t0:
            continue
        a, b = (tm.src_to_ref(t0), tm.src_to_ref(t1)) if tm else (t0, t1)
        total = sum(len(w) + 1 for w in toks)
        pos = a
        for w in toks:
            dt = (b - a) * (len(w) + 1) / total
            words.append({"w": w, "start": round(pos, 3), "end": round(pos + dt, 3)})
            pos += dt
    return words


def language_of(path: Path) -> str:
    """Sprachkürzel aus dem Dateinamen (`Folge.de.srt`, `…_deu.ttml`, `…-de-DE.dfxp`); leer = unbekannt."""
    for tok in reversed(re.split(r"[._\- ()\[\]]+", path.stem.lower())):
        tok = LANG_ALIASES.get(tok, tok)
        if tok in {"de", "en", "fr", "es", "it"}:
            return tok
    return ""


def find_candidates(media_path: Path) -> list[Path]:
    """Untertitel-Dateien neben einer Videodatei mit gleichem Namensanfang, Deutsch zuerst."""
    d = media_path.parent
    if not d.is_dir():
        return []
    stem = media_path.stem.lower()
    found = [f for f in d.iterdir() if f.suffix.lower() in SUB_EXT and f.is_file() and f.stem.lower().startswith(stem)]
    return sorted(found, key=lambda f: (language_of(f) != "de", f.name.lower()))
