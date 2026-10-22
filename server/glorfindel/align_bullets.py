"""Abgleich für Stichpunkt-Skripte: Der Sprecher formuliert frei aus, Wortlaut und Skript passen nicht.

Statt Wort-Alignment wird das Transkript in Sprechgruppen zerlegt und per Schlüsselwort-Ähnlichkeit
(IDF-gewichtet, auf Wortstämme gekürzt) monoton den Stichpunkten in Skriptreihenfolge zugeordnet
(dynamische Programmierung). Retakes: Cluster mit großer Pause trennen, der letzte gewinnt.
Der gesprochene Text kann anschließend als Skript übernommen werden (`adopt_spoken`).
"""
from __future__ import annotations

import math

from .align import norm_words

STOPWORDS = set(norm_words(
    "der die das den dem des ein eine einer einen einem eines und oder aber auch noch nur dass wenn weil als wie "
    "wir ihr sie er es ich du man ist sind war waren wird werden wurde wurden hat haben hatte hatten kann können "
    "nicht kein keine mit von zu zum zur bei nach vor auf aus für über unter durch gegen ohne sich dann dort hier "
    "also sehr schon mal ja nein doch genau eigentlich einfach ganz mehr immer wieder gibt gab seine "
    "ihre seinen ihren diese dieser diesen dieses jetzt heute damit dabei dazu davon darum deshalb okay"))


def stems(text: str) -> set[str]:
    return {w[:6] for w in norm_words(text) if len(w) >= 4 and w not in STOPWORDS}


def make_chunks(tr: list[dict], max_words: int = 14, gap: float = 0.6) -> list[tuple[int, int]]:
    """Transkript in Sprechgruppen teilen (Pausen oder Maximallänge). Rückgabe: [(start_idx, end_idx_exkl)]."""
    chunks, s = [], 0
    for i in range(1, len(tr) + 1):
        if i == len(tr) or tr[i]["start"] - tr[i - 1]["end"] > gap or i - s >= max_words:
            chunks.append((s, i))
            s = i
    return chunks


def monotone_assign(gain: list[list[float]], tau: float) -> list[int | None]:
    """gain[i][j] = Ähnlichkeit Chunk i / Einheit j. Zuordnung nicht fallend in j; Chunks dürfen offen bleiben."""
    n = len(gain)
    m = len(gain[0]) if n else 0
    NEG = -1e18
    dp = [[0.0] * m for _ in range(n + 1)]
    choice = [[-1] * m for _ in range(n + 1)]  # -1: Chunk nicht zugeordnet, sonst Vorgängerzustand
    for i in range(1, n + 1):
        pm, arg = NEG, 0
        for j in range(m):
            if dp[i - 1][j] >= pm:  # bei Gleichstand späteren Zustand bevorzugen
                pm, arg = dp[i - 1][j], j
            a = gain[i - 1][j] - tau
            assign = pm + a + 1e-6 * i if a > 0 else NEG  # kleiner Bonus: spätere Chunks (letzter Take)
            if assign > dp[i - 1][j]:
                dp[i][j], choice[i][j] = assign, arg
            else:
                dp[i][j] = dp[i - 1][j]
    j = max(range(m), key=lambda k: dp[n][k]) if m else 0
    out: list[int | None] = [None] * n
    for i in range(n, 0, -1):
        c = choice[i][j]
        if c == -1:
            continue
        out[i - 1] = j
        j = c
    return out


def align_bullets(units: list[tuple[str, int, list[str]]], tr: list[dict], rec_id: str,
                  tau: float = 0.25, preroll: float = 0.15, postroll: float = 0.30,
                  retake_gap: float = 8.0) -> dict[str, list[dict]]:
    """`units`: [(scene_id, block_idx, stichpunkte)] in Lesereihenfolge (eines Sprechers).

    Ergebnis wie `align_recording`; je Block zusätzlich `stichpunkte` [{idx,in,out,score,matched,word_start}],
    `gesprochen` (Transkript des Blocks) und `words` (Transkriptwörter mit Zeiten).
    """
    out: dict[str, list[dict]] = {}
    flat = [(sid, bi, k, stems(b)) for sid, bi, bullets in units for k, b in enumerate(bullets)]
    if not tr or not flat:
        for sid, bi, _ in units:
            out.setdefault(sid, []).append({"block": bi, "rec": rec_id, "missing": True})
        return out
    flat_index = {(f[0], f[1], f[2]): j for j, f in enumerate(flat)}
    chunks = make_chunks(tr)
    cstems = [stems(" ".join(w["w"] for w in tr[a:b])) for a, b in chunks]
    df: dict[str, int] = {}
    for st in cstems + [f[3] for f in flat]:
        for s_ in st:
            df[s_] = df.get(s_, 0) + 1
    total = len(chunks) + len(flat)
    idf = {s_: math.log(1 + total / c) for s_, c in df.items()}
    gain: list[list[float]] = []
    for cs in cstems:
        row = []
        for f in flat:
            denom = sum(idf[s_] for s_ in f[3])
            row.append(sum(idf[s_] for s_ in cs & f[3]) / denom if denom else 0.0)
        gain.append(row)
    assign = monotone_assign(gain, tau)

    by_block: dict[tuple[str, int], dict[int, list[int]]] = {}
    for ci, u in enumerate(assign):
        if u is not None:
            sid, bi, k, _ = flat[u]
            by_block.setdefault((sid, bi), {}).setdefault(k, []).append(ci)

    for sid, bi, bullets in units:
        hit = by_block.get((sid, bi))
        if not hit:
            out.setdefault(sid, []).append({"block": bi, "rec": rec_id, "missing": True})
            continue
        all_c = sorted(c for cl in hit.values() for c in cl)
        clusters, cur = [], [all_c[0]]
        for c in all_c[1:]:
            if tr[chunks[c][0]]["start"] - tr[chunks[cur[-1]][1] - 1]["end"] > retake_gap:
                clusters.append(cur)
                cur = []
            cur.append(c)
        clusters.append(cur)
        keep = set(clusters[-1])  # letzter Take
        w0, w1 = chunks[min(keep)][0], chunks[max(keep)][1]
        words_tr = tr[w0:w1]
        per_bullet, last_in = [], None
        for k in range(len(bullets)):
            cs = [c for c in hit.get(k, []) if c in keep]
            if cs:
                last_in = tr[chunks[min(cs)][0]]["start"]
                score = max(gain[c][flat_index[(sid, bi, k)]] for c in cs)
                per_bullet.append({"idx": k, "in": last_in, "score": round(score, 3), "matched": True})
            else:
                per_bullet.append({"idx": k, "in": last_in if last_in is not None else tr[w0]["start"],
                                   "score": 0.0, "matched": False})
        for k, pb in enumerate(per_bullet):
            pb["out"] = per_bullet[k + 1]["in"] if k + 1 < len(per_bullet) else tr[w1 - 1]["end"]
            pb["word_start"] = next((i for i, w in enumerate(words_tr) if w["start"] >= pb["in"] - 1e-6), 0)
        matched = sum(1 for pb in per_bullet if pb["matched"])
        out.setdefault(sid, []).append({
            "block": bi, "rec": rec_id,
            "in": round(max(0.0, tr[w0]["start"] - preroll), 3),
            "out": round(tr[w1 - 1]["end"] + postroll, 3),
            "confidence": round(matched / max(1, len(per_bullet)), 3),
            "uncertain": matched < len(per_bullet),
            "takes": [{"start": tr[chunks[cl[0]][0]]["start"], "end": tr[chunks[cl[-1]][1] - 1]["end"]}
                      for cl in clusters],
            "chosen": len(clusters) - 1,
            "stichpunkte": per_bullet,
            "gesprochen": " ".join(w["w"] for w in words_tr),
            "words": [{"i": i, "start": w["start"], "end": w["end"]} for i, w in enumerate(words_tr)],
            "ergaenzungen": [],
        })
    return out


def adopt_spoken(block, result: dict) -> None:
    """Übernimmt den gesprochenen Text als Skript; Stichpunkt-Anker wandern auf Wortindizes."""
    starts = {b["idx"]: b["word_start"] for b in result["stichpunkte"]}
    n_words = len(result["gesprochen"].split())
    for a in block.anker:
        if a.einheit == "stichpunkt":
            a.von = starts.get(a.von, 0)
            a.bis = starts.get(a.bis, n_words) if a.bis is not None else None
            a.einheit = "wort"
    block.text = result["gesprochen"]
    block.gesprochen = result["gesprochen"]
    block.modus = "text"
