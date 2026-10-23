"""Szenenerkennung fürs Strang-Board (Heft §5.2): PySceneDetect + Tonpausen -> Szenen-Vorschläge."""
from __future__ import annotations

import re
from pathlib import Path

from . import media


def detect_shots(video: Path, threshold: float = 27.0, min_scene_len: int = 8, on_progress=None) -> list[tuple[float, float]]:
    """Schnitte per ContentDetector. Gibt [(start_s, end_s)] zurück. Am besten auf dem 540p-Proxy.
    `on_progress(fraction, text)` wird etwa zweimal pro Sekunde aufgerufen."""
    import threading
    import time

    from scenedetect import ContentDetector, SceneManager, open_video
    stream = open_video(str(video))
    sm = SceneManager()
    sm.add_detector(ContentDetector(threshold=threshold, min_scene_len=min_scene_len))
    total = max(1, getattr(stream.duration, "frame_num", None) or stream.duration.get_frames()) if stream.duration else 1
    err: list[BaseException] = []

    def work():
        try:
            sm.detect_scenes(stream)
        except BaseException as e:  # noqa: BLE001
            err.append(e)
    th = threading.Thread(target=work, daemon=True)
    th.start()
    t0 = time.time()
    while th.is_alive():
        th.join(0.5)
        if on_progress:
            f = min(0.99, stream.frame_number / total)
            el = time.time() - t0
            fps = stream.frame_number / el if el > 0.5 else 0
            on_progress(f, f"Bild {stream.frame_number:,} von {total:,}".replace(",", ".") + (f" · {fps:.0f} Bilder/s" if fps else ""))  # Abbruch-Ausnahme beendet nur das Warten
    if err:
        raise err[0]
    scenes = sm.get_scene_list()
    if not scenes:
        return [(0.0, media.probe(video)["duration"])]
    return [(a.seconds, b.seconds) for a, b in scenes]


def detect_silences(video: Path, noise_db: int = -35, min_len: float = 0.8, on_progress=None) -> list[tuple[float, float]]:
    try:
        dur = media.probe(video)["duration"]
    except Exception:  # noqa: BLE001
        dur = None
    r = media.run_ffmpeg(["ffmpeg", "-v", "info", "-i", str(video), "-vn", "-af",
                          f"silencedetect=noise={noise_db}dB:d={min_len}", "-f", "null", "-"], dur,
                         (lambda f, info: on_progress(f, info["text"])) if on_progress else None)
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", r.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", r.stderr)]
    return list(zip(starts, ends[:len(starts)]))


def propose_scenes(shots: list[tuple[float, float]], silences: list[tuple[float, float]],
                   min_len: float = 15.0, density_window: float = 20.0, silence_tol: float = 1.0) -> list[dict]:
    """Shots zu Szenen bündeln: Grenze an einem Schnitt, der (a) in/neben einer Tonpause liegt oder
    (b) auf einen Wechsel in der Schnittdichte folgt; Szenen kürzer als `min_len` werden angehängt."""
    if not shots:
        return []

    def near_silence(t: float) -> bool:
        return any(s - silence_tol <= t <= e + silence_tol for s, e in silences)

    def cut_density(t0: float, t1: float) -> float:
        n = sum(1 for a, _ in shots if t0 <= a < t1)
        return n / max(t1 - t0, 1e-6)

    bounds = [shots[0][0]]
    for i in range(1, len(shots)):
        t = shots[i][0]
        if t - bounds[-1] < min_len:
            continue
        before = cut_density(max(bounds[-1], t - density_window), t)
        after = cut_density(t, t + density_window)
        jump = abs(after - before) > 0.5 * max(before, after, 1e-6) and max(before, after) > 0.08
        if near_silence(t) or jump:
            bounds.append(t)
    end = shots[-1][1]
    scenes = []
    for i, b in enumerate(bounds):
        e = bounds[i + 1] if i + 1 < len(bounds) else end
        if e - b < min_len and scenes:
            scenes[-1]["end"] = e
            continue
        scenes.append({"start": round(b, 3), "end": round(e, 3)})
    for s in scenes:
        s["shots"] = [round(a, 3) for a, _ in shots if s["start"] <= a < s["end"]]
    return scenes


def thumbnails(video: Path, times: list[float], out_dir: Path, width: int = 240, on_progress=None) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    res = []
    for k, t in enumerate(times):
        if on_progress:
            on_progress(k, len(times))
        dst = out_dir / f"th_{int(t * 1000):09d}.jpg"
        if not dst.exists():
            media.extract_frame(video, t, dst, width=width)
        res.append(dst)
    return res
