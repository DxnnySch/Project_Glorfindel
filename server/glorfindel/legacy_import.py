"""Import bestehender Word-Skripte im bisherigen Format (Heft §5.6, Einstieg für laufende Folgen).

Format der Skripte (S2 E7):
  [Szenenhinweis]          neue Szene, Text in Klammern = Titel/Cue (auch Zitate: [„They have a Ravager“])
  P: Text …  /  D: Text …  Sprecherwechsel (Philipp/Danny); ohne Präfix bleibt der Sprecher gleich
  [Intro] [Werbung] [CREDITS] …  Rahmenteile -> freie Blöcke
  - Stichpunkt / • Stichpunkt  Stichpunkt-Skript (wird frei gesprochen)
Text vor der ersten Klammer (Cold Open) wird ein freier Block.
Segmente (In/Out) fehlen im Word-Skript; sie werden danach im Szenen-Editor gesetzt.
"""
from __future__ import annotations

import re
from pathlib import Path

from docx import Document

from .models import CommentBlock, Scene
from .scenes import parse_bullets

_CUE_RE = re.compile(r"^\s*\[(.+?)\]\s*(.*)$", re.S)
_SPEAKER_RE = re.compile(r"^\s*(P|D|Philipp|Danny)\s*:\s*", re.I)
FRAME_WORDS = ("intro", "werbung", "outro", "abspann", "credits", "cold open", "coldopen", "spoiler", "abo")
SPEAKER = {"p": "philipp", "philipp": "philipp", "d": "danny", "danny": "danny"}


def is_frame_cue(cue: str) -> bool:
    c = cue.lower()
    return any(w in c for w in FRAME_WORDS) and len(c) < 40


def parse_legacy_script(path: Path | str, default_speaker: str = "philipp") -> dict:
    """Gibt {'scenes': [Scene…] (ohne Segmente), 'free_blocks': [...], 'stats': {...}} zurück."""
    doc = Document(str(path))
    scenes: list[Scene] = []
    free: list[dict] = []
    speaker = default_speaker
    cur_scene: Scene | None = None
    cur_free: dict | None = None
    buf: list[str] = []          # Absätze desselben Sprechers im aktuellen Abschnitt
    buf_speaker, buf_is_bullet = speaker, False

    def flush():
        nonlocal buf
        if not buf:
            return
        text = "\n".join(buf).strip()
        buf = []
        if cur_scene is not None:
            bullets = parse_bullets(text)
            blk = (CommentBlock(sprecher=buf_speaker, modus="stichpunkte", stichpunkte=bullets) if bullets  # type: ignore[arg-type]
                   else CommentBlock(sprecher=buf_speaker, text=" ".join(text.split())))                    # type: ignore[arg-type]
            cur_scene.kommentar.append(blk)
        elif cur_free is not None:
            cur_free["text"] += ("\n" if cur_free["text"] else "") + text

    for p in doc.paragraphs:
        text = p.text.strip()
        if not text:
            continue
        m = _CUE_RE.match(text)
        if m:
            flush()
            cue, rest = m.group(1).strip(), m.group(2).strip()
            if is_frame_cue(cue):
                cur_scene = None
                cur_free = {"after": scenes[-1].id if scenes else None, "titel": cue, "text": ""}
                free.append(cur_free)
            else:
                cur_free = None
                cur_scene = Scene(id=f"sz_{len(scenes) + 1:02d}", titel=cue, reihenfolge=len(scenes))
                scenes.append(cur_scene)
            text = rest
            if not text:
                continue
        elif cur_scene is None and cur_free is None:
            cur_free = {"after": None, "titel": "Cold Open", "text": ""}
            free.append(cur_free)
        sm = _SPEAKER_RE.match(text)
        if sm:
            flush()
            speaker = SPEAKER[sm.group(1).lower()]
            text = text[sm.end():].strip()
        if not text:
            continue
        is_bullet = bool(parse_bullets(text))
        if buf and is_bullet != buf_is_bullet:
            flush()  # Stichpunkte und Fließtext getrennt halten
        if not buf:
            buf_speaker, buf_is_bullet = speaker, is_bullet
        buf.append(text)
    flush()
    # Absätze desselben Sprechers hintereinander = ein Block (Abschnitt je Sprecherwechsel)
    for sc in scenes:
        merged: list[CommentBlock] = []
        for b in sc.kommentar:
            if merged and merged[-1].sprecher == b.sprecher and merged[-1].modus == b.modus == "text":
                merged[-1].text += " " + b.text
            else:
                merged.append(b)
        sc.kommentar = merged
    words = sum(len(b.text.split()) for sc in scenes for b in sc.kommentar)
    return {"scenes": scenes, "free_blocks": free,
            "stats": {"scenes": len(scenes), "free_blocks": len(free), "words": words}}
