"""Arbeitsdateien in OneDrive teilen und Projekte auf einem zweiten Rechner automatisch erkennen."""
import shutil

from glorfindel.config import Settings
from glorfindel.service import Episode, detect_episodes_dir, list_episodes
from conftest import make_clip, needs_ffmpeg


def _second_machine(settings: Settings, tmp_path) -> Settings:
    """Gleicher OneDrive-Ordner, aber eigener lokaler Cache (anderer Rechner)."""
    s = settings.model_copy(deep=True)
    s.user = "maurice"
    return s


def test_work_dir_in_onedrive_and_local_when_off(episode_root):
    ep = Episode.create(episode_root, 2, 7)
    assert ep.p.work() == ep.p.gl / "arbeit"
    assert ep.proxy_path("q1").parent == ep.p.gl / "arbeit"
    episode_root.share_work_files = False
    assert Episode(episode_root, 2, 7).p.work() == ep.p.cache()


def test_adopts_old_local_files(episode_root):
    ep = Episode.create(episode_root, 2, 8)
    (ep.p.cache() / "proxy_q1.mp4").write_bytes(b"x")
    (ep.p.cache() / "board.json").write_text("{}")
    from glorfindel.paths import EpisodePaths
    EpisodePaths._adopted.clear()
    w = ep.p.work()
    assert (w / "proxy_q1.mp4").exists() and (w / "board.json").exists()
    assert not (ep.p.cache() / "proxy_q1.mp4").exists()


def test_detect_episodes_dir_from_arbitrary_root(tmp_path):
    root = tmp_path / "OneDrive"
    ep_dir = root / "Mythen-Archiv" / "Videos" / "S2 E7" / "glorfindel"
    ep_dir.mkdir(parents=True)
    (ep_dir / "projekt.json").write_text("{}")
    assert detect_episodes_dir(root) == "Mythen-Archiv/Videos"
    assert detect_episodes_dir(tmp_path / "leer") is None
    s = Settings(onedrive_root=str(root), episodes_dir="Falsch")
    assert list_episodes(s) == []
    s.episodes_dir = detect_episodes_dir(root)
    assert [e["episode"] for e in list_episodes(s)] == [7]


@needs_ffmpeg
def test_proxy_shared_between_machines(episode_root, tmp_path, monkeypatch):
    ep = Episode.create(episode_root, 2, 7)
    ref = make_clip(tmp_path / "OneDrive" / "ref.mp4")
    from glorfindel import service
    src = ep.import_source(str(ref), "referenz")
    out = ep.ensure_proxy(src.id)
    assert out.exists() and out.parent == ep.p.gl / "arbeit"
    assert not (ep.p.cache() / f"proxy_{src.id}.mp4").exists()     # lokale Kodierdatei aufgeräumt
    # zweiter Rechner: eigener lokaler Cache, derselbe OneDrive-Ordner -> Proxy sofort da, kein neues Kodieren
    monkeypatch.setenv("GLORFINDEL_HOME", str(tmp_path / "home2"))
    ep2 = Episode(_second_machine(episode_root, tmp_path), 2, 7)
    called = []
    monkeypatch.setattr(service.media, "make_proxy", lambda *a, **k: called.append(1))
    assert ep2.proxy_path(src.id).exists()
    ep2.ensure_proxy(src.id)
    assert not called


def test_proxy_lock_by_other_machine(episode_root, monkeypatch):
    import pytest
    from glorfindel import store
    ep = Episode.create(episode_root, 2, 9)
    ep.p.ensure()
    store.acquire_lock(ep.p.locks, "proxy_q1", "maurice")
    with pytest.raises(RuntimeError, match="maurice"):
        ep.ensure_proxy("q1")
