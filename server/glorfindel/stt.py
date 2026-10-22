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


def parse_verbose(resp, offset: float) -> list[dict]:
    """Wörter aus einer verbose_json-Antwort (Objekt oder dict) mit Zeitversatz des Stücks."""
    get = (lambda o, k: o.get(k)) if isinstance(resp, dict) else (lambda o, k: getattr(o, k, None))
    words = get(resp, "words") or []
    out = []
    for w in words:
        word, start, end = get(w, "word"), get(w, "start"), get(w, "end")
        if word is None or start is None:
            continue
        out.append({"w": str(word).strip(), "start": round(float(start) + offset, 3),
                    "end": round(float(end if end is not None else start) + offset, 3), "p": 1.0})
    return [w for w in out if w["w"]]


def transcribe_remote(path: Path, client, model: str = REMOTE_MODEL, language: str = "de",
                      glossary: str = align.TOLKIEN_GLOSSARY, progress_cb=None) -> list[dict]:
    words: list[dict] = []
    with tempfile.TemporaryDirectory() as td:
        chunks = split_audio(path, Path(td))
        for k, (f, offset) in enumerate(chunks):
            with open(f, "rb") as fh:
                resp = client.audio.transcriptions.create(
                    model=model, file=fh, language=language, prompt=glossary,
                    response_format="verbose_json", timestamp_granularities=["word"])
            words += parse_verbose(resp, offset)
            if progress_cb:
                progress_cb((k + 1) / len(chunks))
    return words


def choose_backend(setting: str) -> str:
    """'lokal' | 'scads'. 'auto': lokal bei CUDA-GPU und installiertem faster-whisper, sonst ScaDS."""
    if setting in ("lokal", "scads"):
        return setting
    try:
        import ctranslate2
        import faster_whisper  # noqa: F401
        if ctranslate2.get_cuda_device_count() > 0:
            return "lokal"
    except Exception:  # noqa: BLE001
        pass
    return "scads"
