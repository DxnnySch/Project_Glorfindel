import shutil
import subprocess
from pathlib import Path

import pytest

needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg fehlt")


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("GLORFINDEL_HOME", str(tmp_path / "home"))


def make_clip(path: Path, seconds: float = 6, fps: int = 24, size: str = "320x136", tone: int = 440):
    """Synthetisches Testvideo: Testbild mit Zeitcode + Sinuston."""
    path.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-v", "error",
           "-f", "lavfi", "-i", f"testsrc2=size={size}:rate={fps}:duration={seconds}",
           "-f", "lavfi", "-i", f"sine=frequency={tone}:duration={seconds}:sample_rate=48000",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path)]
    subprocess.run(cmd, check=True)
    return path


@pytest.fixture
def clip(tmp_path):
    return make_clip(tmp_path / "clip.mp4")


@pytest.fixture
def episode_root(tmp_path):
    from glorfindel.config import Settings
    root = tmp_path / "OneDrive"
    root.mkdir()
    return Settings(onedrive_root=str(root))
