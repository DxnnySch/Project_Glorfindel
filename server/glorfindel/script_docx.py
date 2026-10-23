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

from .scenes import segment_of
from .models import AssetRef, CommentBlock, Scene

SPEAKERS = {"philipp": "PHILIPP", "danny": "DANNY"}
_LABEL_RE = re.compile(r"^\s*(PHILIPP|DANNY)\s*:\s*", re.I)
_SZ_RE = re.compile(r"⟦sz:([^⟧]+)⟧")
_SG_RE = re.compile(r"⟦sg:(\d+)⟧")
_MARK_RE = re.compile(r"⟦([+-])(bild|karte):([^|⟧~]+)(?:~[^|⟧]*)?(?:\|([^⟧]+))?⟧")
GREY = RGBColor(0x99, 0x99, 0x99)


def fmt_tc(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def _label(ident: str, labels: dict[str, str] | None) -> str:
    """Lesbarer Zusatz hinter der ID (ohne Leerzeichen), z. B. art_0001~Alan_Lee."""
    name = (labels or {}).get(ident, "")
    name = re.sub(r"[\s|⟦⟧~]+", "_", name).strip("_")[:40]
    return f"{ident}~{name}" if name else ident


def _bullet_marks(block: CommentBlock, labels: dict[str, str] | None = None) -> dict[int, list[str]]:
    marks: dict[int, list[str]] = {}
    for a in block.anker:
        kind, ident = ("bild", a.asset) if a.asset else ("karte", a.karte)
        if not ident:
            continue
        lay = f"|{a.layout}" if a.layout != "einzel" else ""
        marks.setdefault(a.von, []).append(f"⟦+{kind}:{_label(ident, labels)}{lay}⟧")
        if a.bis is not None:
            marks.setdefault(a.bis, []).append(f"⟦-{kind}:{ident}⟧")
    return marks


def _marked_words(block: CommentBlock, labels: dict[str, str] | None = None) -> list[tuple[str, str]]:
    """Liste von (typ, inhalt): ('w', wort) oder ('m', markentext) in Lesereihenfolge."""
    words = block.text.split()
    marks: dict[int, list[str]] = {}
    for a in block.anker:
        kind, ident = ("bild", a.asset) if a.asset else ("karte", a.karte)
        if not ident:
            continue
        lay = f"|{a.layout}" if a.layout != "einzel" else ""
        marks.setdefault(min(a.von, len(words)), []).append(f"⟦+{kind}:{_label(ident, labels)}{lay}⟧")
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
                tc_start: dict[str, float] | None = None, labels: dict[str, str] | None = None) -> None:
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
        def write_blocks(blocks):
            for block in blocks:
                if speaker and block.sprecher != speaker:
                    continue
                p = doc.add_paragraph()
                lab = p.add_run(SPEAKERS[block.sprecher] + ":")
                lab.bold = True
                if block.modus == "stichpunkte":
                    marks = _bullet_marks(block, labels)
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
                for typ, val in _marked_words(block, labels):
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

        if sc.segmente:
            for si, seg in enumerate(sc.segmente):
                head = doc.add_paragraph()
                hr = head.add_run(f"Segment {si + 1}  ·  {fmt_tc(seg.in_)}–{fmt_tc(seg.out)}" + (f"  ·  Notiz: {seg.notiz}" if seg.notiz else "") + f"  ⟦sg:{si}⟧")
                hr.bold = True
                hr.font.size = Pt(10)
                hr.font.color.rgb = GREY
                write_blocks([b for b in sc.kommentar if segment_of(b, sc) == si])
        else:
            write_blocks(sc.kommentar)
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
    cur_seg: int | None = None
    for p in doc.paragraphs:
        text = _para_text(p)
        style = p.style.name if p.style is not None else ""
        if style == "Heading 1":
            m = _SZ_RE.search(text)
            if m:
                cur_scene, cur_free = m.group(1), None
                titel = _SZ_RE.sub("", text).strip()
                titel = re.sub(r"^Szene\s+\d+\s*[–-]\s*", "", titel)
                res.scenes[cur_scene] = {"titel": titel, "kommentar": [], "notizen": {}}
                cur_seg = None
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
            sg = _SG_RE.search(text)
            if sg and text.lstrip().startswith("Segment"):
                cur_seg = int(sg.group(1))
                nm = re.search(r"Notiz:\s*(.*?)\s*⟦sg", text)
                res.scenes[cur_scene]["notizen"][cur_seg] = nm.group(1) if nm else ""
                continue
            lm = _LABEL_RE.match(text)
            blocks = res.scenes[cur_scene]["kommentar"]
            if lm:
                rest = text[lm.end():]
                if not rest.strip():   # Label allein -> Stichpunkte folgen
                    blocks.append(CommentBlock(sprecher=lm.group(1).lower(), modus="stichpunkte", segment=cur_seg))  # type: ignore[arg-type]
                    open_bullet_marks.clear()
                else:
                    nb = _parse_block(lm.group(1), rest)
                    nb.segment = cur_seg
                    blocks.append(nb)
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
            return [(c.sprecher, c.modus, c.text, tuple(c.stichpunkte), segment_of(c, sc),
                     [(a.asset, a.karte, a.von, a.bis) for a in c.anker]) for c in cs]
        if any(b.segment is None for b in new) and sc.segmente:  # Dokument ohne Segmentmarken: Zuordnung behalten
            for nb, ob in zip(new, sc.kommentar):
                if nb.segment is None:
                    nb.segment = ob.segment
        old_sig, new_sig = sig(sc.kommentar), sig(new)
        title_changed = data["titel"] and data["titel"] != (sc.titel or sc.id)
        notes_changed = any(0 <= i < len(sc.segmente) and sc.segmente[i].notiz != n for i, n in (data.get("notizen") or {}).items())
        if notes_changed:
            for i, n in data["notizen"].items():
                if 0 <= i < len(sc.segmente):
                    sc.segmente[i].notiz = n
        if old_sig != new_sig or title_changed or notes_changed:
            for nb, ob in zip(new, sc.kommentar):   # Aufnahme-Ergebnis (gesprochen) nicht verlieren
                if not nb.gesprochen and nb.modus == ob.modus:
                    nb.gesprochen = ob.gesprochen
            sc.kommentar = new
            if title_changed:
                sc.titel = data["titel"]
            changed.append(sid)
    return changed


def export_speaker_docx(scenes: list[Scene], path, title: str = "", speaker: str | None = None,
                        labels: dict[str, str] | None = None, free_blocks: list[dict] | None = None,
                        dialog_of=None, regie: bool = True) -> None:
    """Lesbares Sprecherskript: Regieanweisungen je Segment, Kommentartext ohne technische Marken,
    Bild-/Kartenhinweise als Randnotiz. Wird nicht zurückgespielt – der Sprecher darf frei ändern.
    `dialog_of(t0, t1) -> str` liefert den gesprochenen Dialog der Stelle (aus dem Episoden-Transkript)."""
    doc = Document()
    doc.styles["Normal"].font.name = "Calibri"
    doc.styles["Normal"].font.size = Pt(15)
    doc.add_heading(title or "Sprecherskript", level=0)
    if speaker:
        p = doc.add_paragraph()
        r = p.add_run(f"Sprecher: {SPEAKERS.get(speaker, speaker)}")
        r.bold = True
    free_after: dict[str | None, list[dict]] = {}
    for fb in free_blocks or []:
        free_after.setdefault(fb.get("after"), []).append(fb)

    def add_free(key):
        for fb in free_after.get(key, []):
            h = doc.add_paragraph()
            r = h.add_run(f"– {fb.get('titel') or 'Pause'}" + (f" ({int(fb['dauer'])} Sekunden)" if fb.get("dauer") else "") + " –")
            r.italic = True
            r.font.color.rgb = GREY

    def note(text: str, color=GREY, size=10.5, italic=True):
        p = doc.add_paragraph()
        r = p.add_run(text)
        r.italic = italic
        r.font.size = Pt(size)
        r.font.color.rgb = color
        return p

    def anchor_note(block: CommentBlock) -> list[str]:
        words = block.text.split()
        out = []
        for a in block.anker:
            ident = a.asset or a.karte
            name = (labels or {}).get(ident, ident)
            kind = "Karte" if a.karte else "Bild"
            if block.modus == "stichpunkte":
                where = f"bei Stichpunkt {a.von + 1}"
            else:
                snippet = " ".join(words[a.von:a.von + 4]) if a.von < len(words) else ""
                where = f"ab „{snippet} …“" if snippet else "am Anfang"
            out.append(f"{kind}: {name} – {where}")
        return out

    add_free(None)
    for n, sc in enumerate(scenes, 1):
        doc.add_heading(f"{n}. {sc.titel or sc.id}", level=1)
        segs = sc.segmente or [None]
        for si, seg in enumerate(segs):
            blocks = [b for b in sc.kommentar if (segment_of(b, sc) == si) and (not speaker or b.sprecher == speaker)]
            if seg is not None and (regie or blocks):
                if regie:
                    dlg = dialog_of(seg.in_, seg.out) if dialog_of else ""
                    parts = [f"Segment {si + 1}"]
                    if seg.notiz:
                        parts.append(seg.notiz)
                    note("Regie · " + " – ".join(parts))
                    if dlg:
                        note(f"Im Bild wird gesagt: „{dlg}“", size=9.5)
            for b in blocks:
                if b.modus == "stichpunkte":
                    if not speaker:
                        doc.add_paragraph().add_run(SPEAKERS[b.sprecher] + ":").bold = True
                    for bullet in b.stichpunkte:
                        doc.add_paragraph(bullet, style="List Bullet")
                else:
                    p = doc.add_paragraph()
                    if not speaker:
                        p.add_run(SPEAKERS[b.sprecher] + ": ").bold = True
                    p.add_run(b.text)
                for line in anchor_note(b):
                    note("Einblendung → " + line, size=9.5)
        add_free(sc.id)
    doc.save(str(path))
