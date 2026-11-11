"""Szenenerkennung fürs Strang-Board (Heft §5.2): PySceneDetect + Tonpausen -> Szenen-Vorschläge."""
from __future__ import annotations

import re
from pathlib import Path

from . import media


def _make_dissolve_detector():
    """Detektor für weiche Blenden. ContentDetector vergleicht nur benachbarte Bilder; bei einer Blende
    ändert sich jedes Bild nur wenig, die Summe über Sekunden aber stark. Hier wird deshalb jedes Bild mit
    dem von ca. `window_s` Sekunden davor verglichen (kleines Graubild). Gemeldet wird der Beginn der Blende."""
    from collections import deque

    import cv2
    import numpy as np
    from scenedetect import SceneDetector

    class DissolveDetector(SceneDetector):
        def __init__(self, window_s: float = 1.0, threshold: float = 28.0, hard: float = 20.0,
                     smooth: float = 10.0, min_gap_s: float = 1.0):
            super().__init__()
            self.window_s, self.thr, self.hard, self.smooth, self.min_gap_s = window_s, threshold, hard, smooth, min_gap_s
            self.buf: deque = deque()
            self.prev = None
            self.k = 0
            self.n = 0
            self.base_n = None        # Beginn des aktuellen Anstiegs (kleinster Abstand)
            self.base_w = 0.0
            self.peak = 0.0
            self.hist: list[tuple[int, float]] = []
            self.cooldown = False
            self.last_cut = -10 ** 9
            self.suppress_until = -1
            self.emitted: list[float] = []

        def _refine(self, n: int, w: float) -> int:
            """Anstieg von 50 % bis 100 % der Höhe als Gerade bis zur Ausgangshöhe zurückverlängern."""
            h = self.base_w + 0.5 * (w - self.base_w)
            t1 = next(((m, x) for m, x in self.hist if x >= h), None)
            if not t1 or n - t1[0] < 2:
                return self.base_n
            slope = (w - t1[1]) / (n - t1[0])
            if slope <= 0:
                return self.base_n
            return max(self.base_n, int(round(t1[0] - (t1[1] - self.base_w) / slope)))

        @property
        def event_buffer_length(self) -> int:
            return int(self.k * 2) + 2

        def process_frame(self, timecode, frame_img):
            fps = timecode.frame_rate
            if not self.k:
                self.k = max(4, round(self.window_s * fps))
            g = cv2.resize(cv2.cvtColor(frame_img, cv2.COLOR_BGR2GRAY), (32, 18), interpolation=cv2.INTER_AREA).astype(np.float32)
            n = self.n = self.n + 1
            cuts = []
            c = float(np.abs(g - self.prev).mean()) if self.prev is not None else 0.0
            self.prev = g
            self.buf.append(g)
            if len(self.buf) > self.k + 1:
                self.buf.popleft()
            if c > self.hard:                      # harter Schnitt: Sache des ContentDetectors
                self.suppress_until = n + self.k
                self.base_n = None
                self.cooldown = False
            if len(self.buf) < self.k + 1:
                return cuts
            w = float(np.abs(g - self.buf[0]).mean())
            if self.base_n is None or w <= self.base_w or n - self.base_n > 2 * self.k or n <= self.suppress_until:
                self.base_n, self.base_w, self.peak = n, w, w   # neuer Ausgangspunkt
                self.hist = [(n, w)]
                self.cooldown = self.cooldown and n <= self.suppress_until
                return cuts
            self.peak = max(self.peak, w)
            self.hist.append((n, w))
            if w < self.peak - 3.0:                  # Anstieg bricht ab: von hier neu beginnen
                self.base_n, self.base_w, self.peak = n, w, w
                self.hist = [(n, w)]
                self.cooldown = False
                return cuts
            if c >= self.smooth:                     # ruckartig statt gleitend: keine Blende
                self.base_n, self.base_w, self.peak = n, w, w
                self.hist = [(n, w)]
                return cuts
            if w - self.base_w >= self.thr and not self.cooldown:
                start = self._refine(n, w)
                if start - self.last_cut >= self.min_gap_s * fps:
                    tc = timecode - (n - start)
                    cuts.append(tc)
                    self.emitted.append(tc.seconds)
                    self.last_cut = start
                self.cooldown = True
            return cuts

    return DissolveDetector()


def detect_shots(video: Path, threshold: float = 27.0, min_scene_len: int = 8, on_progress=None,
                 dissolves: bool = True) -> list[tuple[float, float]]:
    """Schnitte per ContentDetector (harte Schnitte) plus Blendendetektor (weiche Blenden).
    Gibt [(start_s, end_s)] zurück. Am besten auf dem 540p-Proxy.
    `on_progress(fraction, text)` wird etwa zweimal pro Sekunde aufgerufen."""
    import threading
    import time

    from scenedetect import ContentDetector, SceneManager, open_video
    stream = open_video(str(video))
    sm = SceneManager()
    sm.add_detector(ContentDetector(threshold=threshold, min_scene_len=min_scene_len))
    dd = _make_dissolve_detector() if dissolves else None
    if dd:
        sm.add_detector(dd)
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
    shots = [(a.seconds, b.seconds) for a, b in scenes]
    if dd and dd.emitted:
        shots = _merge_dissolve_cuts(shots, dd.emitted)
    return shots


def _merge_dissolve_cuts(shots: list[tuple[float, float]], dissolve_starts: list[float], span: float = 2.0) -> list[tuple[float, float]]:
    """Der ContentDetector meldet oft das Ende einer kurzen Blende; der Beginn zählt, das spätere Ergebnis fällt weg."""
    ds = set(round(d, 3) for d in dissolve_starts)
    cuts = [a for a, _ in shots[1:]]
    keep = []
    for c in cuts:
        if round(c, 3) not in ds and any(d < c <= d + span for d in ds):
            continue
        keep.append(c)
    edges = [shots[0][0]] + keep + [shots[-1][1]]
    return [(edges[i], edges[i + 1]) for i in range(len(edges) - 1)]


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
