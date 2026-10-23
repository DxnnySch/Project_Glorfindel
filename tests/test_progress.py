"""Detaillierter Fortschritt: Schritte, Teilschritte, Gewichte, Restzeit, Abbruch, ffmpeg-Live-Fortschritt."""
import time

import pytest

from glorfindel import media
from glorfindel.progress import Abgebrochen, Progress, as_progress, overall, view

needs_ffmpeg = pytest.mark.skipif(not media.shutil.which("ffmpeg"), reason="ffmpeg fehlt")


def _job():
    return {"id": "x", "name": "t", "status": "laeuft", "started": time.time() - 10, "finished": None, "result": None, "error": ""}


def test_legacy_call_sets_overall():
    j = _job()
    p = Progress(j)
    p(0.4)
    assert overall(j) == 0.4 and view(j)["progress"] == 0.4


def test_weighted_steps_and_sub():
    j = _job()
    p = Progress(j).plan([("A", 1), ("B", 3)])
    p.step("A")
    p.sub(1, 2, "halb", "Dateien")
    assert abs(overall(j) - 0.5 * 0.25) < 1e-6
    p.step("B")                      # A gilt als fertig
    v = view(j)
    assert v["steps"][0]["status"] == "fertig" and v["step_index"] == 2 and v["step_total"] == 2 and v["step_name"] == "B"
    assert abs(v["progress"] - 0.25) < 1e-6
    p.fraction(0.5)
    assert abs(overall(j) - (0.25 + 0.75 * 0.5)) < 1e-6


def test_eta_needs_progress_and_time():
    j = _job()                       # läuft seit 10 s
    p = Progress(j).plan(["A"])
    p.step(0)
    p.fraction(0.5)
    v = view(j)
    assert 8 < v["eta"] < 12 and v["elapsed"] >= 10
    j2 = _job()
    Progress(j2).plan(["A"]).step(0)
    assert view(j2)["eta"] is None   # noch kein Fortschritt: keine Schätzung


def test_skip_and_dynamic_step_and_cancel():
    j = _job()
    p = Progress(j).plan(["A", "B"])
    p.step(0)
    p.skip("B")
    p.step("C")                      # unbekannter Name wird angehängt
    assert [s["name"] for s in view(j)["steps"]] == ["A", "B", "C"]
    j["cancel"] = True
    with pytest.raises(Abgebrochen):
        p.detail("x")


def test_as_progress_wraps_none_and_functions():
    assert isinstance(as_progress(None), Progress)
    seen = []
    q = as_progress(lambda f: seen.append(f))
    q.plan(["A"])
    q.step(0)
    q.fraction(0.5)
    assert seen and abs(seen[-1] - 0.5) < 1e-6


@needs_ffmpeg
def test_ffmpeg_live_progress(tmp_path):
    src = tmp_path / "a.mp4"
    media.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=d=3:s=160x120:r=24", "-pix_fmt", "yuv420p", str(src)])
    got = []
    r = media.run_ffmpeg(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-c:v", "libx264", str(tmp_path / "b.mp4")], 3.0, lambda f, i: got.append((f, i)))
    assert r.returncode == 0 and got and got[-1][0] > 0.9 and "von 0:03" in got[-1][1]["text"]


@needs_ffmpeg
def test_ffmpeg_cancel_kills_process(tmp_path):
    src = tmp_path / "a.mp4"
    media.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=d=20:s=640x360:r=24", "-pix_fmt", "yuv420p", str(src)])

    def boom(f, i):
        raise Abgebrochen("stop")
    with pytest.raises(Abgebrochen):
        media.run_ffmpeg(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-c:v", "libx264", "-preset", "veryslow", str(tmp_path / "b.mp4")], 20.0, boom)


def test_job_view_over_api(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from glorfindel.api import create_app
    monkeypatch.setenv("GLORFINDEL_HOME", str(tmp_path))
    c = TestClient(create_app())
    st = c.app.state.gl

    def work(progress):
        progress.plan([("Eins", 1), ("Zwei", 1)])
        progress.step(0, "erst")
        progress.sub(1, 4, "Datei a", "Dateien")
        progress.step(1, "dann")
        return "ok"
    jid = st.jobs.submit("demo", work)
    for _ in range(50):
        j = c.get(f"/api/jobs/{jid}").json()
        if j["status"] == "fertig":
            break
        time.sleep(0.05)
    assert j["status"] == "fertig" and j["progress"] == 1.0 and j["elapsed"] >= 0
    assert [s["status"] for s in j["steps"]] == ["fertig", "fertig"] and j["step_total"] == 2
    assert "_fixed" not in j and "trace" not in j
