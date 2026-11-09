"""Dialog der Episode (Transkript der Referenz): speichern, abfragen, Text zu Zeitbereichen, Transkriptions-Auftrag."""
from __future__ import annotations

from pathlib import Path

from . import align, media, stt, store, subtitles
from .progress import as_progress
from .service import Episode


def path(ep: Episode) -> Path:
    return ep.p.gl / "dialog.json"


path_of = path   # `path` wird in Funktionen von Parametern verdeckt


def load(ep: Episode) -> dict:
    return store.read_json(path(ep), {"sprache": "", "quelle": "", "words": []})


def text_between(words: list[dict], t0: float, t1: float, pad: float = 0.1) -> str:
    """Gesprochene Wörter, die (überwiegend) in [t0, t1] liegen."""
    sel = [w["w"] for w in words if w["end"] > t0 - pad and w["start"] < t1 + pad and (w["start"] + w["end"]) / 2 >= t0 - pad and (w["start"] + w["end"]) / 2 <= t1 + pad]
    return " ".join(sel).strip()


def subtitle_candidates(ep: Episode) -> list[dict]:
    """Untertitel-Dateien neben den Quelldateien (z. B. von Amazon): [{source, path, sprache}]."""
    out = []
    for s in ep.sources():
        f = ep.source_path(s)
        for c in subtitles.find_candidates(f):
            out.append({"source": s.id, "path": str(c), "sprache": subtitles.language_of(c)})
    return out


def import_subtitles(ep: Episode, path: str | Path, source_id: str | None = None) -> dict:
    """Untertitel als Dialog übernehmen (statt zu transkribieren). Zeiten der Quelle -> Episodenzeit über deren Anker."""
    from .paths import to_abs
    f = to_abs(ep.p.root, str(path))
    if not f.is_file():
        raise FileNotFoundError(f"Untertitel nicht gefunden: {f}")
    sid = source_id or next((c["source"] for c in subtitle_candidates(ep) if Path(c["path"]) == f), None) \
        or ep.project().reference_source
    if not sid:
        raise ValueError("Keine Quelle für die Untertitel gewählt.")
    from .timemap import TimeMap
    tm = TimeMap(ep.source(sid).anchors)
    words = subtitles.cues_to_words(subtitles.parse_file(f), tm)
    if not words:
        raise RuntimeError(f"In {f.name} wurden keine Untertitel gefunden.")
    lang = subtitles.language_of(f)
    store.write_json(path_of(ep), {"sprache": lang, "quelle": sid, "untertitel": f.name, "words": words})
    store.log_change(ep.p.gl, ep.settings.user, f"Dialog aus Untertiteln übernommen ({f.name}, {len(words)} Wörter)")
    return {"words": len(words), "datei": f.name, "sprache": lang}


def transcribe(ep: Episode, llm=None, sprache: str = "auto", progress=None, subtitles_first: bool = True) -> dict:
    pg = as_progress(progress)
    if subtitles_first:                                  # Untertitel vorhanden: keine Transkription nötig
        cands = [c for c in subtitle_candidates(ep) if sprache in ("", "auto") or c["sprache"] in ("", sprache)]
        if cands:
            pg.plan([("Untertitel übernehmen", 1)])
            pg.step(0, Path(cands[0]["path"]).name)
            return import_subtitles(ep, cands[0]["path"], cands[0]["source"])
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
