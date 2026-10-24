"""ffmpeg/ffprobe-Hilfen: Probe, Proxy, Stills, Thumbnails, Fingerabdruck, OneDrive-Prüfung."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path


def _bin(name: str) -> str:
    p = shutil.which(name)
    if not p:
        raise RuntimeError(f"{name} nicht gefunden (install.ps1/install.sh ausführen)")
    return p


def run(cmd: list[str], timeout: float | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                          encoding="utf-8", errors="replace")


def fmt_clock(seconds: float) -> str:
    s = int(max(0, seconds))
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def run_ffmpeg(cmd: list[str], duration: float | None = None, on_progress=None) -> subprocess.CompletedProcess:
    """ffmpeg mit Live-Fortschritt. `on_progress(fraction, info)`; info: {"t": s, "speed": x-fach, "fps": f, "text": "…"}.
    Eine Ausnahme im Callback (z. B. Abbruch) beendet ffmpeg."""
    import tempfile
    full = [cmd[0], "-progress", "pipe:1", "-nostats"] + cmd[1:]
    with tempfile.TemporaryFile("w+", encoding="utf-8", errors="replace") as err:
        p = subprocess.Popen(full, stdout=subprocess.PIPE, stderr=err, text=True, encoding="utf-8", errors="replace")
        t, speed, fps = 0.0, None, None
        try:
            for line in p.stdout:  # type: ignore[union-attr]
                k, _, v = line.strip().partition("=")
                if k in ("out_time_us", "out_time_ms") and v.lstrip("-").isdigit():
                    t = max(0.0, int(v) / 1_000_000)
                elif k == "speed" and v.endswith("x"):
                    try:
                        speed = float(v[:-1])
                    except ValueError:
                        pass
                elif k == "fps":
                    try:
                        fps = float(v)
                    except ValueError:
                        pass
                elif k == "progress" and on_progress:
                    frac = min(1.0, t / duration) if duration else 0.0
                    txt = f"{fmt_clock(t)}" + (f" von {fmt_clock(duration)}" if duration else "") + (f" · {speed:.1f}× Echtzeit" if speed else "")
                    on_progress(frac, {"t": t, "speed": speed, "fps": fps, "text": txt})
            p.wait()
        except BaseException:
            p.kill()
            p.wait()
            raise
        err.seek(0)
        return subprocess.CompletedProcess(full, p.returncode, "", err.read())


def run_bytes(cmd: list[str], timeout: float | None = None) -> bytes:
    r = subprocess.run(cmd, capture_output=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"{Path(cmd[0]).name} fehlgeschlagen: {r.stderr.decode(errors='replace')[-300:]}")
    return r.stdout


def _fraction(s: str) -> float:
    try:
        n, _, d = s.partition("/")
        return float(n) / float(d) if d else float(n)
    except (ValueError, ZeroDivisionError):
        return 0.0


def probe(path: Path | str) -> dict:
    r = run([_bin("ffprobe"), "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)])
    if r.returncode != 0:
        raise RuntimeError(f"ffprobe fehlgeschlagen: {r.stderr.strip()[:300]}")
    j = json.loads(r.stdout)
    v = next((s for s in j.get("streams", []) if s.get("codec_type") == "video" and s.get("width")), None)
    a = next((s for s in j.get("streams", []) if s.get("codec_type") == "audio"), None)
    dur = float(j.get("format", {}).get("duration") or (v or {}).get("duration") or 0)
    fps = _fraction((v or {}).get("avg_frame_rate", "0")) or _fraction((v or {}).get("r_frame_rate", "0"))
    return {
        "duration": dur, "fps": fps,
        "width": int((v or {}).get("width", 0)), "height": int((v or {}).get("height", 0)),
        "has_audio": a is not None, "has_video": v is not None,
        "vcodec": (v or {}).get("codec_name", ""),
    }


def wait_until_stable(path: Path, checks: int = 3, interval: float = 1.0, timeout: float = 600.0, on_check=None) -> bool:
    """Wartet, bis eine OneDrive-Datei vollständig synchronisiert ist (Größe stabil, lesbar)."""
    end = time.time() + timeout
    last, same = -1, 0
    while time.time() < end:
        try:
            size = path.stat().st_size
            with open(path, "rb") as f:
                f.read(1)
        except OSError:
            same, last = 0, -1
            time.sleep(interval)
            continue
        same = same + 1 if size == last else 0
        last = size
        if on_check:
            on_check(min(same, checks), checks, size)
        if same >= checks:
            return True
        time.sleep(interval)
    return False


def is_online_only(path: Path) -> bool:
    """Windows: OneDrive „Dateien bei Bedarf“ (Platzhalter ohne lokale Daten)."""
    try:
        import ctypes
        attrs = ctypes.windll.kernel32.GetFileAttributesW(str(path))  # type: ignore[attr-defined]
        if attrs == -1:
            return False
        RECALL_ON_DATA_ACCESS, OFFLINE = 0x400000, 0x1000
        return bool(attrs & (RECALL_ON_DATA_ACCESS | OFFLINE))
    except Exception:
        return False


def fingerprint(path: Path, seconds: float = 20.0) -> str:
    """Audio-Fingerabdruck: Hash über ein grob quantisiertes 8-kHz-Mono-Signal aus der Dateimitte.

    Robust gegen Container-/Umbenennungsänderungen; nicht gegen Neukodierung (dafür ist der Pfad da).
    """
    try:
        dur = probe(path)["duration"]
    except Exception:
        return ""
    start = max(0.0, dur / 2 - seconds / 2)
    r = subprocess.run(
        [_bin("ffmpeg"), "-v", "error", "-ss", f"{start:.2f}", "-t", f"{seconds}", "-i", str(path),
         "-vn", "-ac", "1", "-ar", "8000", "-f", "u8", "-"],
        capture_output=True,
    )
    if not r.stdout:
        return ""
    q = bytes(b >> 5 for b in r.stdout)  # grob quantisieren
    return hashlib.sha1(q).hexdigest()[:16]


def detect_crop(path: Path, samples: int = 5) -> list[int] | None:
    """Schwarze Ränder erkennen (cropdetect an mehreren Stellen) -> [x, y, w, h] oder None."""
    import re
    dur = probe(path)["duration"]
    votes: dict[tuple[int, int, int, int], int] = {}
    for i in range(samples):
        t = dur * (i + 1) / (samples + 1)
        r = run([_bin("ffmpeg"), "-v", "info", "-ss", f"{t:.1f}", "-i", str(path), "-t", "2",
                 "-vf", "cropdetect=limit=24:round=2:reset=0", "-an", "-f", "null", "-"], timeout=120)
        m = re.findall(r"crop=(\d+):(\d+):(\d+):(\d+)", r.stderr)
        if m:
            w, h, x, y = (int(v) for v in m[-1])
            votes[(x, y, w, h)] = votes.get((x, y, w, h), 0) + 1
    if not votes:
        return None
    x, y, w, h = max(votes, key=votes.get)
    info = probe(path)
    if (w, h) == (info["width"], info["height"]):
        return None
    return [x, y, w, h]


def video_filter(height: int | None = None, crop: list[int] | None = None, fps: float | None = None) -> str:
    """Gemeinsamer Filter für Proxys: zuschneiden, auf konstante Bildrate bringen, skalieren."""
    parts = []
    if crop:
        x, y, w, h = crop
        parts.append(f"crop={w}:{h}:{x}:{y}")
    if fps:
        parts.append(f"fps={fps}")
    if height:
        parts.append(f"scale=-2:{height}")
    return ",".join(parts) or "null"


def make_proxy(src: Path, dst: Path, height: int = 540, crop: list[int] | None = None,
               fps: float | None = None, on_progress=None) -> Path:
    """540p H.264, jeder Frame ein Keyframe (-g 1) für exaktes Scrubben/Frame-Stepping.

    `crop` und `fps` normalisieren Bildschirmaufnahmen (variable Bildrate, Letterbox) auf die Folge.
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(".part.mp4")
    # Ton immer Mono: Stereo-AAC macht Firefox beim Springen in langen Dateien extrem langsam (Sekunden bis Hänger),
    # Mono springt in Millisekunden. Für ein Arbeits-Proxy reicht Mono. Datenspuren/Kapitel (Timecode) bleiben draußen.
    cmd = [_bin("ffmpeg"), "-y", "-v", "error", "-i", str(src), "-map", "0:v:0", "-map", "0:a:0?",
           "-vf", video_filter(height, crop, fps), "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
           "-g", "1", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "96k", "-ac", "1",
           "-write_tmcd", "0", "-map_chapters", "-1", "-movflags", "+faststart", str(tmp)]
    try:
        dur = probe(src)["duration"]
    except Exception:  # noqa: BLE001
        dur = None
    try:
        r = run_ffmpeg(cmd, dur, on_progress)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    if r.returncode != 0:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"Proxy fehlgeschlagen: {r.stderr.strip()[:300]}")
    tmp.replace(dst)
    return dst


def proxy_needs_fix(path: Path) -> bool:
    """Alte Proxys mit Stereo-Ton oder Datenspuren (Firefox springt darin sehr langsam) erkennen."""
    r = run([_bin("ffprobe"), "-v", "error", "-show_entries", "stream=codec_type,channels", "-of", "json", str(path)])
    try:
        streams = json.loads(r.stdout).get("streams", [])
    except ValueError:
        return False
    return any((st.get("codec_type") == "audio" and st.get("channels", 1) > 1) or st.get("codec_type") == "data"
               for st in streams)


def fix_proxy_audio(path: Path, on_progress=None) -> Path:
    """Ton auf Mono umstellen und Datenspuren entfernen; das Bild wird nur kopiert (Minuten statt Stunden)."""
    tmp = path.with_suffix(".fix.mp4")
    cmd = [_bin("ffmpeg"), "-y", "-v", "error", "-i", str(path), "-map", "0:v:0", "-map", "0:a:0?", "-c:v", "copy",
           "-c:a", "aac", "-b:a", "96k", "-ac", "1", "-write_tmcd", "0", "-map_chapters", "-1",
           "-movflags", "+faststart", str(tmp)]
    try:
        dur = probe(path)["duration"]
    except Exception:  # noqa: BLE001
        dur = None
    try:
        r = run_ffmpeg(cmd, dur, on_progress)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    if r.returncode != 0:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"Proxy-Anpassung fehlgeschlagen: {r.stderr.strip()[:300]}")
    tmp.replace(path)
    return path


def extract_frame(src: Path, t: float, dst: Path, width: int | None = None, fps_hint: float | None = None) -> Path:
    """Einzelbild bei Zeit t (s) als PNG/JPG; -ss nach -i für Frame-Genauigkeit bei langen Dateien
    wird vermieden, indem Eingangssuche + Dekodier-Verwerfen genutzt wird (Standard in ffmpeg)."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = [_bin("ffmpeg"), "-y", "-v", "error", "-ss", f"{max(0.0, t):.4f}", "-i", str(src), "-frames:v", "1"]
    if width:
        cmd += ["-vf", f"scale={width}:-2"]
    tmp = dst.with_name(dst.stem + ".part" + dst.suffix)
    cmd += [str(tmp)]
    r = run(cmd)
    if r.returncode != 0 or not tmp.exists():
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"Frame-Export fehlgeschlagen: {r.stderr.strip()[:300]}")
    try:
        os.replace(tmp, dst)
    except PermissionError as e:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"Die Datei {dst.name} ist gesperrt (von Premiere oder OneDrive verwendet): {dst}") from e
    return dst


def extract_still_last_frame(src: Path, t_end: float, fps: float, dst: Path, size: tuple[int, int] | None = None) -> Path:
    """Letzter Frame einer Szene = Frame direkt vor dem Schnitt `t_end`.

    ffmpeg liefert bei Eingangs-Suche das erste Bild mit PTS >= Zielzeit. Das letzte Bild hat die PTS `t_end - 1/fps`; Ziel
    ist deshalb `t_end - 1.5/fps`: genau zwischen der PTS des Vorgängers und der des gewollten Bildes (robust gegen Rundung)."""
    t = max(0.0, t_end - (1.5 / fps if fps else 0.06))
    extract_frame(src, t, dst)
    if size:
        from PIL import Image
        im = Image.open(dst)
        if im.size != size:
            im.resize(size, Image.LANCZOS).save(dst)
    return dst


def waveform_peaks(src: Path, buckets: int = 2000, sr: int = 4000) -> list[float]:
    """Wellenform für die Prüfansicht (max. Betrag je Bucket, 0..1)."""
    import numpy as np
    r = subprocess.run([_bin("ffmpeg"), "-v", "error", "-i", str(src), "-vn", "-ac", "1", "-ar", str(sr),
                        "-f", "s16le", "-"], capture_output=True)
    x = np.frombuffer(r.stdout, dtype=np.int16).astype(np.float32) / 32768.0
    if x.size == 0:
        return []
    n = max(1, x.size // buckets)
    x = x[: n * buckets] if x.size >= n * buckets else x
    peaks = np.abs(x[: (x.size // n) * n].reshape(-1, n)).max(axis=1)
    return [round(float(p), 4) for p in peaks]
