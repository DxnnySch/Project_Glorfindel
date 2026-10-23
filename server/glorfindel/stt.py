"""Transkriptions-Backends: lokal (faster-whisper) oder ScaDS.AI (OpenAI-kompatibles Whisper).

Das Remote-Backend sendet Audio an ScaDS.AI und ist nur aktiv, wenn es in den Einstellungen gewählt
wird („Transkription: ScaDS“) oder bei „auto“ lokal keine geeignete GPU vorhanden ist.
"""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from . import align, media

CHUNK_S = 600.0       # 10-Minuten-Stücke bleiben deutlich unter üblichen Upload-Limits
REMOTE_MODEL = "openai/whisper-large-v3-turbo"


def split_audio(src: Path, dst_dir: Path, chunk_s: float = CHUNK_S) -> list[tuple[Path, float]]:
    """16 kHz Mono MP3 in Stücken; Rückgabe: [(Datei, Offset in s)]."""
    dur = media.probe(src)["duration"]
    out, t, i = [], 0.0, 0
    while t < dur - 0.05:
        dst = dst_dir / f"chunk_{i:03d}.mp3"
        r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.3f}", "-t", f"{chunk_s:.3f}", "-i", str(src),
                            "-vn", "-ac", "1", "-ar", "16000", "-b:a", "48k", str(dst)], capture_output=True)
        if r.returncode != 0 or not dst.exists():
            raise RuntimeError("Audio konnte nicht aufgeteilt werden")
        out.append((dst, t))
        t += chunk_s
        i += 1
    return out


def words_from_segments(segments, offset: float) -> list[dict]:
    """Ersatz, wenn der Dienst keine Wort-Zeitstempel liefert (ScaDS-Whisper tut das nicht): Die Wörter eines
    Segments werden nach Zeichenlänge auf dessen Zeitspanne verteilt. Für Anzeige und Abgleich genau genug."""
    get = (lambda o, k: o.get(k)) if isinstance(segments[0], dict) else (lambda o, k: getattr(o, k, None))
    out = []
    for sg in segments:
        text, start, end = (get(sg, "text") or "").strip(), get(sg, "start"), get(sg, "end")
        if not text or start is None or end is None:
            continue
        if (get(sg, "no_speech_prob") or 0) > 0.8 and (get(sg, "avg_logprob") or 0) < -1.0:
            continue  # Musik/Geräusche, vom Modell selbst als „keine Sprache“ eingestuft
        toks = text.split()
        weights = [len(t) + 1 for t in toks]
        total, t = float(sum(weights)), float(start)
        span = max(float(end) - float(start), 0.05)
        for tok, wgt in zip(toks, weights):
            d = span * wgt / total
            out.append({"w": tok, "start": round(t + offset, 3), "end": round(t + d + offset, 3), "p": 0.5})
            t += d
    return out


def parse_verbose(resp, offset: float) -> list[dict]:
    """Wörter aus einer verbose_json-Antwort (Objekt oder dict) mit Zeitversatz des Stücks.
    Fehlen Wort-Zeitstempel, werden sie aus den Segment-Zeiten abgeleitet."""
    get = (lambda o, k: o.get(k)) if isinstance(resp, dict) else (lambda o, k: getattr(o, k, None))
    out = []
    for w in get(resp, "words") or []:
        word, start, end = get(w, "word"), get(w, "start"), get(w, "end")
        if word is None or start is None:
            continue
        out.append({"w": str(word).strip(), "start": round(float(start) + offset, 3),
                    "end": round(float(end if end is not None else start) + offset, 3), "p": 1.0})
    out = [w for w in out if w["w"]]
    if not out:
        segs = get(resp, "segments") or []
        if segs:
            out = words_from_segments(segs, offset)
    return out


def transcribe_remote(path: Path, client, model: str = REMOTE_MODEL, language: str | None = "de",
                      glossary: str = align.TOLKIEN_GLOSSARY, progress_cb=None) -> list[dict]:
    words: list[dict] = []
    with tempfile.TemporaryDirectory() as td:
        chunks = split_audio(path, Path(td))
        for k, (f, offset) in enumerate(chunks):
            with open(f, "rb") as fh:
                kw = {k: v for k, v in (("language", language), ("prompt", glossary or None)) if v}
                resp = client.audio.transcriptions.create(
                    model=model, file=fh, response_format="verbose_json", timestamp_granularities=["word"], **kw)
            words += parse_verbose(resp, offset)
            if progress_cb:
                progress_cb((k + 1) / len(chunks))
    return words


def choose_backend(setting: str) -> str:
    """'lokal' | 'scads' | 'keins'. 'auto' wählt nie ScaDS (Audio verlässt den Rechner nur auf ausdrückliche Anweisung)."""
    if setting in ("lokal", "scads"):
        return setting
    try:
        import faster_whisper  # noqa: F401
        return "lokal"
    except Exception:  # noqa: BLE001
        return "keins"
