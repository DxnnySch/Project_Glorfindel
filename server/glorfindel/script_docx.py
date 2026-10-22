"""Word-Export für die Aufnahme und Rückimport (Heft §5.6).

Szenen-Kopfzeilen tragen die Marke ⟦sz:ID⟧. Asset-/Kartenanker stehen als kleine graue Marken
⟦+bild:ID|layout⟧ … ⟦-bild:ID⟧ an Wortgrenzen im Text und überstehen so den Roundtrip.
Überschriften ohne Szenenmarke werden beim Import zu freien Blöcken (Intro, Werbung, Outro …).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from docx import Document
from docx.enum.text import WD_COLOR_INDEX
from docx.shared import Pt, RGBColor

from .models import AssetRef, CommentBlock, Scene

SPEAKERS = {"philipp": "PHILIPP", "danny": "DANNY"}
_LABEL_RE = re.compile(r"^\s*(PHILIPP|DANNY)\s*:\s*", re.I)
_SZ_RE = re.compile(r"⟦sz:([^⟧]+)⟧")
_MARK_RE = re.compile(r"⟦([+-])(bild|karte):([^|⟧]+)(?:\|([^⟧]+))?⟧")
GREY = RGBColor(0x99, 0x99, 0x99)


def fmt_tc(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def _bullet_marks(block: CommentBlock) -> dict[int, list[str]]:
    marks: dict[int, list[str]] = {}
    for a in block.anker:
        kind, ident = ("bild", a.asset) if a.asset else ("karte", a.karte)
        if not ident:
            continue
        lay = f"|{a.layout}" if a.layout != "einzel" else ""
        marks.setdefault(a.von, []).append(f"⟦+{kind}:{ident}{lay}⟧")
        if a.bis is not None:
            marks.setdefault(a.bis, []).append(f"⟦-{kind}:{ident}⟧")
    return marks


def _marked_words(block: CommentBlock) -> list[tuple[str, str]]:
    """Liste von (typ, inhalt): ('w', wort) oder ('m', markentext) in Lesereihenfolge."""
    words = block.text.split()
    marks: dict[int, list[str]] = {}
    for a in block.anker:
        kind, ident = ("bild", a.asset) if a.asset else ("karte", a.karte)
        if not ident:
            continue
        lay = f"|{a.layout}" if a.layout != "einzel" else ""
        marks.setdefault(min(a.von, len(words)), []).append(f"⟦+{kind}:{ident}{lay}⟧")
        if a.bis is not None:
            marks.setdefault(min(a.bis, len(words)), []).append(f"⟦-{kind}:{ident}⟧")
    out: list[tuple[str, str]] = []
    for i in range(len(words) + 1):
        for m in marks.get(i, []):
            out.append(("m", m))
        if i < len(words):
            out.append(("w", words[i]))
    return out


def export_docx(scenes: list[Scene], path, title: str = "", speaker: str | None = None,
                show_markers: bool = True, free_blocks: list[dict] | None = None,
                tc_start: dict[str, float] | None = None) -> None:
    """`free_blocks`: [{'after': 'sz_07'|None, 'titel': str, 'text': str}] werden eingefügt."""
    doc = Document()
    doc.styles["Normal"].font.name = "Calibri"
    doc.styles["Normal"].font.size = Pt(14)
    if title:
        doc.add_heading(title, level=0)
    free_after: dict[str | None, list[dict]] = {}
    for fb in free_blocks or []:
        free_after.setdefault(fb.get("after"), []).append(fb)

    def add_free(key):
        for fb in free_after.get(key, []):
            doc.add_heading(fb.get("titel") or "Freier Block", level=1)
            for para in (fb.get("text") or "").split("\n"):
                if para.strip():
                    doc.add_paragraph(para)

    add_free(None)
    for n, sc in enumerate(scenes, 1):
        h = doc.add_heading(level=1)
        h.add_run(f"Szene {n:02d} – {sc.titel or sc.id}")
        mark = h.add_run(f"  ⟦sz:{sc.id}⟧")
        mark.font.size = Pt(7)
        mark.font.color.rgb = GREY
        meta = doc.add_paragraph()
        tc = fmt_tc(tc_start[sc.id]) if tc_start and sc.id in tc_start else (
            fmt_tc(sc.segmente[0].in_) if sc.segmente else "–")
        r = meta.add_run(f"Strang: {sc.strang or '–'}  ·  TC {tc}  ·  Segmente: {len(sc.segmente)}")
        r.font.size = Pt(9)
        r.font.color.rgb = GREY
        for block in sc.kommentar:
            if speaker and block.sprecher != speaker:
                continue
            p = doc.add_paragraph()
            lab = p.add_run(SPEAKERS[block.sprecher] + ":")
            lab.bold = True
            if block.modus == "stichpunkte":
                marks = _bullet_marks(block)
                for bi, bullet in enumerate(block.stichpunkte):
                    bp = doc.add_paragraph(style="List Bullet")
                    if show_markers:
                        for m in marks.get(bi, []):
                            r = bp.add_run(m + " ")
                            r.font.size = Pt(7)
                            r.font.color.rgb = GREY
                    bp.add_run(bullet)
                continue
            p.add_run(" ")
            first = True
            for typ, val in _marked_words(block):
                if typ == "m":
                    if not show_markers:
                        continue
                    r = p.add_run(("" if first else " ") + val)
                    r.font.size = Pt(7)
                    r.font.color.rgb = GREY
                    first = False
                else:
                    p.add_run(("" if first else " ") + val)
                    first = False
        add_free(sc.id)
    doc.save(str(path))


@dataclass
class ImportResult:
    scenes: dict[str, dict] = field(default_factory=dict)   # id -> {'titel': str, 'kommentar': [CommentBlock]}
    free_blocks: list[dict] = field(default_factory=list)
    order: list[str] = field(default_factory=list)


def _parse_block(label: str, text: str) -> CommentBlock:
    """Wandelt Text mit Marken in Text + Anker (Wortindizes)."""
    words: list[str] = []
    open_marks: dict[tuple[str, str], AssetRef] = {}
    refs: list[AssetRef] = []
    for tok in text.split():
        m = _MARK_RE.fullmatch(tok)
        # Marken können mit angrenzenden Wörtern verklebt sein -> zerlegen
        parts = [tok] if m else re.split(r"(⟦[^⟧]+⟧)", tok)
        for part in parts:
            if not part:
                continue
            mm = _MARK_RE.fullmatch(part)
            if not mm:
                words.append(part)
                continue
            sign, kind, ident, lay = mm.groups()
            key = (kind, ident)
            if sign == "+":
                ref = AssetRef(**({"asset": ident} if kind == "bild" else {"karte": ident}),
                               von=len(words), layout=lay or "einzel")
                open_marks[key] = ref
                refs.append(ref)
            elif key in open_marks:
                open_marks.pop(key).bis = len(words)
    return CommentBlock(sprecher=label.lower(), text=" ".join(words), anker=refs)  # type: ignore[arg-type]


def _parse_bullet(text: str, idx: int, refs: list[AssetRef], open_marks: dict) -> str:
    """Entfernt Marken aus einem Stichpunkt und legt Anker mit Stichpunkt-Index an."""
    def sub(m):
        sign, kind, ident, lay = m.groups()
        key = (kind, ident)
        if sign == "+":
            ref = AssetRef(**({"asset": ident} if kind == "bild" else {"karte": ident}),
                           von=idx, layout=lay or "einzel", einheit="stichpunkt")
            open_marks[key] = ref
            refs.append(ref)
        elif key in open_marks:
            open_marks.pop(key).bis = idx
        return ""
    return _MARK_RE.sub(sub, text).strip()


def _para_text(p) -> str:
    return "".join(r.text for r in p.runs)


def import_docx(path) -> ImportResult:
    doc = Document(str(path))
    res = ImportResult()
    cur_scene: str | None = None
    cur_free: dict | None = None
    prev_scene: str | None = None
    open_bullet_marks: dict = {}
    for p in doc.paragraphs:
        text = _para_text(p)
        style = p.style.name if p.style is not None else ""
        if style == "Heading 1":
            m = _SZ_RE.search(text)
            if m:
                cur_scene, cur_free = m.group(1), None
                titel = _SZ_RE.sub("", text).strip()
                titel = re.sub(r"^Szene\s+\d+\s*[–-]\s*", "", titel)
                res.scenes[cur_scene] = {"titel": titel, "kommentar": []}
                res.order.append(cur_scene)
                prev_scene = cur_scene
            else:
                cur_scene = None
                cur_free = {"after": prev_scene, "titel": text.strip(), "text": ""}
                res.free_blocks.append(cur_free)
            continue
        if style == "Title" or not text.strip():
            continue
        if cur_scene is not None:
            if text.lstrip().startswith("Strang:"):
                continue
            lm = _LABEL_RE.match(text)
            blocks = res.scenes[cur_scene]["kommentar"]
            if lm:
                rest = text[lm.end():]
                if not rest.strip():   # Label allein -> Stichpunkte folgen
                    blocks.append(CommentBlock(sprecher=lm.group(1).lower(), modus="stichpunkte"))  # type: ignore[arg-type]
                    open_bullet_marks.clear()
                else:
                    blocks.append(_parse_block(lm.group(1), rest))
            elif style == "List Bullet" and blocks and blocks[-1].modus == "stichpunkte":
                blk = blocks[-1]
                blk.stichpunkte.append(_parse_bullet(text, len(blk.stichpunkte), blk.anker, open_bullet_marks))
            elif blocks and blocks[-1].modus == "stichpunkte" and not blocks[-1].stichpunkte:
                blocks[-1].modus = "text"
                blocks[-1].text = text.strip()
            elif blocks:  # Fortsetzungsabsatz
                prev = res.scenes[cur_scene]["kommentar"][-1]
                extra = _parse_block(prev.sprecher, text)
                shift = len(prev.text.split())
                for a in extra.anker:
                    a.von += shift
                    a.bis = a.bis + shift if a.bis is not None else None
                prev.text = (prev.text + " " + extra.text).strip()
                prev.anker.extend(extra.anker)
        elif cur_free is not None:
            cur_free["text"] += ("\n" if cur_free["text"] else "") + text
    return res


def apply_import(scenes: list[Scene], res: ImportResult) -> list[str]:
    """Übernimmt geänderte Texte in vorhandene Szenen. Gibt IDs der geänderten Szenen zurück."""
    changed = []
    by_id = {s.id: s for s in scenes}
    for sid, data in res.scenes.items():
        sc = by_id.get(sid)
        if not sc:
            continue
        new = data["kommentar"]
        def sig(cs):
            return [(c.sprecher, c.modus, c.text, tuple(c.stichpunkte),
                     [(a.asset, a.karte, a.von, a.bis) for a in c.anker]) for c in cs]
        old_sig, new_sig = sig(sc.kommentar), sig(new)
        title_changed = data["titel"] and data["titel"] != (sc.titel or sc.id)
        if old_sig != new_sig or title_changed:
            for nb, ob in zip(new, sc.kommentar):   # Aufnahme-Ergebnis (gesprochen) nicht verlieren
                if not nb.gesprochen and nb.modus == ob.modus:
                    nb.gesprochen = ob.gesprochen
            sc.kommentar = new
            if title_changed:
                sc.titel = data["titel"]
            changed.append(sid)
    return changed
