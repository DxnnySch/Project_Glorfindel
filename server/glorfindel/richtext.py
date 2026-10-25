"""Formatierter Kommentartext (kleines Markdown): `plain()` liefert den reinen Sprechtext – Grundlage für Wortzählung, Abgleich und Anker.

Syntax: **fett**, *kursiv*, __unterstrichen__, ~~durchgestrichen~~, [Text]{#rrggbb} (Farbe), [Text]{bg:#rrggbb} (Hervorhebung),
Zeilenanfang: `# `/`## `/`### ` Überschrift, `- ` Aufzählung, `1. ` Nummerierung, `>` Einzug (mehrfach = tiefer).
Die JavaScript-Fassung (web/js/richtext.js) muss genau dasselbe liefern; beide werden mit tests/data/richtext_cases.json geprüft."""
from __future__ import annotations

import re

LINE_PREFIX = re.compile(r"^[ \t]*(?:>+[ \t]*)?(?:#{1,3}[ \t]+|[-•][ \t]+|\d+[.)][ \t]+)?")      # Einzug und/oder Block-Zeichen (darf leer sein)
DETECT = re.compile(r"(?m)^[ \t]*(?:>|#{1,3}[ \t]|[-•][ \t]|\d+[.)][ \t])")
INLINE = re.compile(r"\*\*|__|~~|\*|\[(?=[^\]\n]*\]\{[^}\n]*\})|\]\{[^}\n]*\}")
SIGNS = re.compile(r"\*\*|__|~~|\*[^\s*]|\[[^\]\n]*\]\{[^}\n]*\}")


def has_markup(text: str) -> bool:
    return bool(SIGNS.search(text) or DETECT.search(text))


def plain(markup: str) -> str:
    out = []
    for line in (markup or "").split("\n"):
        out.append(INLINE.sub("", LINE_PREFIX.sub("", line, count=1)))
    return "\n".join(out)
