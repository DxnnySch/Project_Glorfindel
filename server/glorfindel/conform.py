"""HQ-Conform (Heft §4): HQ-Datei so zuschneiden/auffüllen/strecken, dass sie zeitlich exakt zur
Schnittquelle (Referenz, Episodenzeit) passt. Außerdem Standbild-Export aus HQ und Kontrollansicht.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import media
from .timemap import TimeMap

CODECS = {
    "prores": ["-c:v", "prores_ks", "-profile:v", "3", "-pix_fmt", "yuv422p10le", "-c:a", "pcm_s16le"],
    "dnxhr": ["-c:v", "dnxhd", "-profile:v", "dnxhr_hq", "-pix_fmt", "yuv422p", "-c:a", "pcm_s16le"],
    "h264": ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac"],
}
EXT = {"prores": ".mov", "dnxhr": ".mov", "h264": ".mp4"}


@dataclass
class Seg:
    out0: float
    out1: float
    hq0: float | None   # None = Schwarz
    hq1: float | None
    a: float = 1.0      # Geschwindigkeit: hq-Sekunden pro Ausgabesekunde

    @property
    def dur(self) -> float:
        return self.out1 - self.out0


def plan_segments(tm: TimeMap, out_dur: float, hq_dur: float, min_len: float = 1e-3) -> list[Seg]:
    """Zerlegt die Ausgabe [0, out_dur] in Stücke: HQ-Inhalt (linear gemappt) oder Schwarz (außerhalb HQ)."""
    segs: list[Seg] = []
    for pc in tm.pieces_over(0.0, out_dur):
        r0, r1 = max(pc.ref0, 0.0), min(pc.ref1, out_dur)
        if r1 - r0 < min_len:
            continue
        # Bereich der Ausgabe, in dem das gemappte HQ-Intervall [0, hq_dur] getroffen wird
        lo = (0.0 - pc.b) / pc.a
        hi = (hq_dur - pc.b) / pc.a
        v0, v1 = (min(lo, hi), max(lo, hi))
        c0, c1 = max(r0, v0), min(r1, v1)
        if c1 - c0 < min_len:
            segs.append(Seg(r0, r1, None, None))
            continue
        if c0 - r0 >= min_len:
            segs.append(Seg(r0, c0, None, None))
        segs.append(Seg(c0, c1, pc.apply(c0), pc.apply(c1), pc.a))
        if r1 - c1 >= min_len:
            segs.append(Seg(c1, r1, None, None))
    return segs


def build_filtergraph(segs: list[Seg], size: tuple[int, int], fps: float, has_audio: bool = True) -> tuple[str, str]:
    """Gibt (filter_complex, 'v_out')-Teile zurück; Audio-Ausgang heißt [aout] (falls vorhanden)."""
    w, h = size
    parts: list[str] = []
    v_labels, a_labels = [], []
    for i, s in enumerate(segs):
        if s.hq0 is None:
            parts.append(f"color=c=black:s={w}x{h}:r={fps}:d={s.dur:.6f},format=yuv420p[v{i}]")
            if has_audio:
                parts.append(f"anullsrc=r=48000:cl=stereo,atrim=duration={s.dur:.6f},asetpts=PTS-STARTPTS[a{i}]")
        else:
            lo, hi = sorted((s.hq0, s.hq1))
            parts.append(
                f"[0:v]trim=start={lo:.6f}:end={hi:.6f},setpts=(PTS-STARTPTS)/{s.a:.9f},"
                f"scale={w}:{h},fps={fps},trim=duration={s.dur:.6f},setpts=PTS-STARTPTS,format=yuv420p[v{i}]")
            if has_audio:
                tempo = f",atempo={s.a:.9f}" if abs(s.a - 1) > 1e-6 else ""
                parts.append(f"[0:a]atrim=start={lo:.6f}:end={hi:.6f},asetpts=PTS-STARTPTS{tempo},"
                             f"aresample=48000,aformat=channel_layouts=stereo,atrim=duration={s.dur:.6f},"
                             f"asetpts=PTS-STARTPTS[a{i}]")
        v_labels.append(f"[v{i}]")
        a_labels.append(f"[a{i}]")
    n = len(segs)
    if has_audio:
        inter = "".join(f"{v}{a}" for v, a in zip(v_labels, a_labels))
        parts.append(f"{inter}concat=n={n}:v=1:a=1[vout][aout]")
    else:
        parts.append(f"{''.join(v_labels)}concat=n={n}:v=1:a=0[vout]")
    return ";".join(parts), "vout"


def conform(hq: Path, tm: TimeMap, out_dur: float, dst: Path, fps: float = 24000 / 1001,
            codec: str = "prores", size: tuple[int, int] | None = None, progress_cb=None) -> Path:  # progress_cb(frac, info)
    """Erzeugt `dst` (Dauer == out_dur), zeitlich deckungsgleich mit der Schnittquelle."""
    info = media.probe(hq)
    size = size or (info["width"], info["height"])
    segs = plan_segments(tm, out_dur, info["duration"])
    if not segs:
        raise ValueError("Keine Überschneidung zwischen HQ-Datei und Schnittquelle – Anker prüfen")
    fg, _ = build_filtergraph(segs, size, fps, info["has_audio"])
    dst = dst.with_suffix(EXT[codec])
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(dst.stem + ".part" + dst.suffix)
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(hq), "-filter_complex", fg, "-map", "[vout]"]
    if info["has_audio"]:
        cmd += ["-map", "[aout]"]
    cmd += CODECS[codec] + ["-t", f"{out_dur:.6f}", str(tmp)]
    try:
        r = media.run_ffmpeg(cmd, out_dur, progress_cb)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    if r.returncode != 0:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"Conform fehlgeschlagen: {r.stderr.strip()[-600:]}")
    tmp.replace(dst)
    return dst


def render_stills_from_hq(hq: Path, tm: TimeMap, still_times_ref: dict[str, float], out_dir: Path,
                          fps: float, size: tuple[int, int] | None = None) -> dict[str, Path]:
    """Standbilder (letzter Frame je Szene) aus HQ – gleicher Dateiname wie beim Screener."""
    out = {}
    for name, t_ref in still_times_ref.items():
        out[name] = media.extract_still_last_frame(hq, tm.ref_to_src(t_ref), fps, out_dir / name, size)
    return out


def compare_frames(src_a: Path, t_a: float, src_b: Path, t_b: float, tmpdir: Path,
                   crop_a=None, crop_b=None, width: int = 320) -> dict:
    """Kontrollansicht: Ähnlichkeit (Korrelation) und Differenzbild zweier Frames."""
    import numpy as np
    from PIL import Image, ImageChops

    tmpdir.mkdir(parents=True, exist_ok=True)

    def grab(src, t, crop, name):
        p = tmpdir / name
        vf = media.video_filter(None, crop, None)
        cmd = ["ffmpeg", "-y", "-v", "error", "-ss", f"{max(t, 0):.4f}", "-i", str(src),
               "-frames:v", "1", "-vf", f"{vf},scale={width}:-2" if vf != "null" else f"scale={width}:-2", str(p)]
        subprocess.run(cmd, capture_output=True)
        return Image.open(p).convert("L") if p.exists() else None

    a, b = grab(src_a, t_a, crop_a, "cmp_a.png"), grab(src_b, t_b, crop_b, "cmp_b.png")
    if a is None or b is None:
        return {"correlation": None, "error": "Frame nicht lesbar (Zeit außerhalb der Quelle?)"}
    b = b.resize(a.size)
    xa, xb = np.asarray(a, dtype=np.float32).ravel(), np.asarray(b, dtype=np.float32).ravel()
    xa, xb = xa - xa.mean(), xb - xb.mean()
    den = float(np.linalg.norm(xa) * np.linalg.norm(xb))
    corr = float(xa @ xb / den) if den > 1e-6 else 0.0
    diff = ImageChops.difference(a, b)
    diff.save(tmpdir / "cmp_diff.png")
    return {"correlation": corr, "uncertain": corr < 0.8,
            "a": str(tmpdir / "cmp_a.png"), "b": str(tmpdir / "cmp_b.png"), "diff": str(tmpdir / "cmp_diff.png")}
