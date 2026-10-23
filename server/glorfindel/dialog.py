"""Dialog der Episode (Transkript der Referenz): speichern, abfragen, Text zu Zeitbereichen, Transkriptions-Auftrag."""
from __future__ import annotations

from pathlib import Path

from . import align, media, stt, store
from .progress import as_progress
from .service import Episode


def path(ep: Episode) -> Path:
    return ep.p.gl / "dialog.json"


def load(ep: Episode) -> dict:
    return store.read_json(path(ep), {"sprache": "", "quelle": "", "words": []})


def text_between(words: list[dict], t0: float, t1: float, pad: float = 0.1) -> str:
    """Gesprochene Wörter, die (überwiegend) in [t0, t1] liegen."""
    sel = [w["w"] for w in words if w["end"] > t0 - pad and w["start"] < t1 + pad and (w["start"] + w["end"]) / 2 >= t0 - pad and (w["start"] + w["end"]) / 2 <= t1 + pad]
    return " ".join(sel).strip()


def transcribe(ep: Episode, llm=None, sprache: str = "auto", progress=None) -> dict:
    pg = as_progress(progress)
    pg.plan([("Quelle prüfen", 1), ("Dialog transkribieren", 30), ("Speichern", 1)])
    pg.step(0)
    pr = ep.project()
    if not pr.reference_source:
        raise ValueError("Keine Referenz-Episode importiert (Quellen).")
    src = ep.source(pr.reference_source)
    f = ep.proxy_path(src.id)
    audio = f if f.exists() else ep.source_path(src)
    if not audio.exists():
        raise FileNotFoundError(f"Episode nicht gefunden: {src.path}")
    backend = stt.choose_backend(ep.settings.transcription)
    if backend == "keins":
        raise RuntimeError("Für die Transkription fehlt Whisper. Lokal installieren oder in den Einstellungen „ScaDS.AI Whisper“ wählen.")
    label = "Whisper (lokal)" if backend == "lokal" else "ScaDS.AI Whisper"
    dur = src.duration or media.probe(audio)["duration"]
    pg.step(1, f"{label}: Modell laden und Audio lesen …")
    lang = None if sprache in ("", "auto") else sprache

    def cb(fr: float, detail: str | None = None) -> None:
        pg.fraction(fr, f"{label}: {media.fmt_clock(fr * dur)} von {media.fmt_clock(dur)} Dialog erkannt")
    if backend == "scads":
        if llm is None or llm.client is None:
            raise RuntimeError("ScaDS-Transkription gewählt, aber kein API-Schlüssel (.env) gefunden")
        words = stt.transcribe_remote(audio, llm.client, language=lang, glossary="", progress_cb=cb)
    else:
        words = align.transcribe(audio, ep.settings.whisper_model, language=lang, glossary="", progress_cb=cb)
    if not words and dur > 30:
        raise RuntimeError(f"{label} hat keinen gesprochenen Text erkannt. Prüfe die Sprache der Episode oder wähle in den "
                           "Einstellungen ein anderes Transkriptions-Verfahren.")
    pg.step(2, f"{len(words)} Wörter")
    data = {"sprache": sprache, "quelle": src.id, "words": words}
    store.write_json(path(ep), data)
    store.log_change(ep.p.gl, ep.settings.user, f"Dialog der Episode transkribiert ({len(words)} Wörter)")
    return {"words": len(words)}
