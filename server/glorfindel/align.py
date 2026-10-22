"""Aufnahme-Abgleich (Heft §5.7): Whisper-Transkript gegen das Skript ausrichten.

Pro Kommentarblock wird im Transkript das ähnlichste Wortfenster gesucht (Fuzzy, wortweise normalisiert).
Mehrfachtreffer = Retakes (Standard: letzter Take). Innerhalb des Fensters werden Skriptwörter über
difflib den Transkriptwörtern zugeordnet; daraus ergeben sich Zeiten für Asset-Anker.
"""
from __future__ import annotations

import difflib
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from rapidfuzz import fuzz

TOLKIEN_GLOSSARY = (
    "Celebrimbor, Khazad-dûm, Ost-in-Edhil, Eregion, Númenor, Galadriel, Elrond, Sauron, Annatar, Gil-galad, "
    "Durin, Disa, Elendil, Isildur, Míriel, Pharazôn, Rhûn, Mordor, Adar, Arondir, Halbrand, Celeborn, "
    "Mittelerde, Silmaril, Morgoth, Valar, Ringe der Macht, Tolkien"
)


def norm(word: str) -> str:
    w = unicodedata.normalize("NFKD", word.lower())
    w = "".join(ch for ch in w if not unicodedata.combining(ch))
    return re.sub(r"[^\w]", "", w).replace("ß", "ss")


def norm_words(text: str) -> list[str]:
    return [n for n in (norm(w) for w in text.split()) if n]


@dataclass
class Take:
    start_idx: int
    end_idx: int  # exklusiv
    score: float


def find_takes(block_words: list[str], tr_words: list[str], min_score: float = 70.0,
               len_factors=(0.9, 1.0, 1.1)) -> list[Take]:
    """Alle plausiblen Fenster (nach Score, lokale Maxima). Mehrere Treffer = mehrere Takes."""
    L = len(block_words)
    if L == 0 or len(tr_words) < max(2, L // 2):
        return []
    target = " ".join(block_words)
    n = len(tr_words)
    best_at = [0.0] * n
    best_len = [L] * n
    for i in range(n):
        for f in len_factors:
            ln = max(1, int(round(L * f)))
            if i + ln > n + max(2, L // 10):
                continue
            s = fuzz.ratio(target, " ".join(tr_words[i:i + ln]))
            if s > best_at[i]:
                best_at[i], best_len[i] = s, ln
    takes: list[Take] = []
    i = 0
    while i < n:
        if best_at[i] >= min_score:
            j = i
            top = i
            while j < n and best_at[j] >= min_score - 15 and j - i <= max(L, 8):
                if best_at[j] > best_at[top]:
                    top = j
                j += 1
            takes.append(Take(top, min(n, top + best_len[top]), best_at[top]))
            i = max(j, top + max(1, L // 2))
        else:
            i += 1
    return takes


def refine_window(block_words: list[str], tr_words: list[str], take: Take, slack: int = 3) -> Take:
    """Fenster an den Rändern nachziehen: Anfang/Ende dort, wo Skriptwörter wirklich beginnen/enden."""
    first, last = block_words[0], block_words[-1]
    best, best_s = take, take.score
    for ds in range(-slack, slack + 1):
        for de in range(-slack, slack + 1):
            s, e = take.start_idx + ds, take.end_idx + de
            if s < 0 or e > len(tr_words) or e - s < 2:
                continue
            sc = fuzz.ratio(" ".join(block_words), " ".join(tr_words[s:e]))
            # Randwörter müssen stimmen (Bonus), damit keine Fremdwörter mitgenommen werden
            sc += 4 * (fuzz.ratio(first, tr_words[s]) > 80) + 4 * (fuzz.ratio(last, tr_words[e - 1]) > 80)
            if sc > best_s:
                best, best_s = Take(s, e, min(100.0, sc)), sc
    return best


def map_words(block_words: list[str], tr: list[dict], take: Take) -> tuple[list[dict], list[str]]:
    """Skriptwort-Index -> Transkriptzeit. Rückgabe: (words[{i,start,end}], spontane Ergänzungen)."""
    seg = tr[take.start_idx:take.end_idx]
    seg_norm = [norm(w["w"]) for w in seg]
    sm = difflib.SequenceMatcher(a=block_words, b=seg_norm, autojunk=False)
    times: dict[int, tuple[float, float]] = {}
    extras: list[str] = []
    for tag, a0, a1, b0, b1 in sm.get_opcodes():
        if tag == "equal" or (tag == "replace" and a1 - a0 == b1 - b0):
            for k in range(a1 - a0):
                times[a0 + k] = (seg[b0 + k]["start"], seg[b0 + k]["end"])
        elif tag == "replace":  # unterschiedlich lang: proportional verteilen
            for k in range(a1 - a0):
                j = b0 + min(b1 - b0 - 1, int(k * (b1 - b0) / max(1, a1 - a0)))
                times[a0 + k] = (seg[j]["start"], seg[j]["end"])
        elif tag == "insert":
            extras.append(" ".join(seg[j]["w"] for j in range(b0, b1)))
    # Lücken (nur im Skript) linear zwischen Nachbarn interpolieren
    words = []
    known = sorted(times)
    for i in range(len(block_words)):
        if i in times:
            s, e = times[i]
        elif not known:
            s = e = seg[0]["start"] if seg else 0.0
        else:
            prev = max((k for k in known if k < i), default=None)
            nxt = min((k for k in known if k > i), default=None)
            if prev is None:
                s = e = times[nxt][0]
            elif nxt is None:
                s = e = times[prev][1]
            else:
                frac = (i - prev) / (nxt - prev)
                s = e = times[prev][1] + frac * (times[nxt][0] - times[prev][1])
        words.append({"i": i, "start": round(s, 3), "end": round(e, 3)})
    return words, [x for x in extras if x.strip()]


def align_block(block_text: str, tr: list[dict], prefer: str = "last", min_score: float = 70.0,
                after_time: float = 0.0, preroll: float = 0.15, postroll: float = 0.30) -> dict | None:
    """Gibt das Abgleichergebnis für einen Block zurück oder None, wenn nichts passt."""
    bw = norm_words(block_text)
    if not bw:
        return None
    # `tr` bleibt unverändert indiziert; Fenstersuche über normalisierte Wörter (leere ausgelassen)
    keep = [k for k, w in enumerate(tr) if norm(w["w"])]
    tr_clean = [tr[k] for k in keep]
    tr_norm = [norm(w["w"]) for w in tr_clean]
    takes = find_takes(bw, tr_norm, min_score)
    if not takes:
        return None
    takes = [refine_window(bw, tr_norm, t) for t in takes]
    candidates = [t for t in takes if tr_clean[t.start_idx]["start"] >= after_time - 0.5] or takes
    chosen = candidates[-1] if prefer == "last" else max(candidates, key=lambda t: t.score)
    words, extras = map_words(bw, tr_clean, chosen)
    t0 = tr_clean[chosen.start_idx]["start"]
    t1 = tr_clean[chosen.end_idx - 1]["end"]
    return {
        "in": round(max(0.0, t0 - preroll), 3), "out": round(t1 + postroll, 3),
        "confidence": round(chosen.score / 100.0, 3),
        "uncertain": chosen.score < 80.0,
        "takes": [{"start": tr_clean[t.start_idx]["start"], "end": tr_clean[t.end_idx - 1]["end"],
                   "score": round(t.score, 1)} for t in takes],
        "chosen": takes.index(chosen),
        "words": words, "ergaenzungen": extras,
    }


def align_recording(blocks: list[tuple[str, int, str]], tr: list[dict], rec_id: str,
                    prefer: str = "last", min_score: float = 70.0) -> dict[str, list[dict]]:
    """`blocks`: [(scene_id, block_index, text)] in Lesereihenfolge dieses Sprechers.
    Ergebnis: scene_id -> [ {block, rec, in, out, ...} ]. Reihenfolge der Szenen schreitet fort."""
    out: dict[str, list[dict]] = {}
    cursor = 0.0
    for scene_id, bi, text in blocks:
        res = align_block(text, tr, prefer=prefer, min_score=min_score, after_time=0.0)
        if res is None:
            out.setdefault(scene_id, []).append({"block": bi, "rec": rec_id, "missing": True})
            continue
        res.update(block=bi, rec=rec_id)
        cursor = max(cursor, res["out"])
        out.setdefault(scene_id, []).append(res)
    return out


def flatten_for_rough_cut(aligned: dict) -> dict:
    """Entfernt Blöcke ohne Treffer, damit der Rohschnitt sie als „Schätzung“ behandelt."""
    return {"scenes": {sid: [b for b in bl if not b.get("missing")] for sid, bl in aligned.items()}}


# ---------- Transkription ----------
def pick_whisper_model(setting: str = "auto") -> tuple[str, str, str]:
    """(Modell, Gerät, compute_type). GPU: large-v3, sonst CPU: small."""
    if setting not in ("", "auto"):
        return setting, "auto", "default"
    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count() > 0:
            return "large-v3", "cuda", "float16"
    except Exception:
        pass
    return "small", "cpu", "int8"


def transcribe(path: Path, model_name: str = "auto", language: str = "de", glossary: str = TOLKIEN_GLOSSARY,
               progress_cb=None) -> list[dict]:
    """Wort-Zeitstempel via faster-whisper (optional installiert)."""
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise RuntimeError("faster-whisper nicht installiert (uv pip install '.[whisper]')") from e
    name, device, ctype = pick_whisper_model(model_name)
    model = WhisperModel(name, device=device, compute_type=ctype)
    segments, info = model.transcribe(str(path), language=language, word_timestamps=True,
                                      initial_prompt=glossary, vad_filter=True, beam_size=5)
    words = []
    for seg in segments:
        for w in seg.words or []:
            words.append({"w": w.word.strip(), "start": round(w.start, 3), "end": round(w.end, 3),
                          "p": round(getattr(w, "probability", 1.0), 3)})
        if progress_cb and info.duration:
            progress_cb(min(1.0, seg.end / info.duration))
    return words
