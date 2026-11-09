"""Pfade relativ zum OneDrive-Stamm und Ordner einer Folge."""
from __future__ import annotations

import re
import shutil
from pathlib import Path

from .config import Settings, app_dir


def to_rel(root: Path | str, p: Path | str) -> str:
    root, p = Path(root), Path(p)
    try:
        return p.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return p.as_posix()  # außerhalb des Stamms: absolut belassen


def to_abs(root: Path | str, rel: str) -> Path:
    p = Path(rel)
    return p if p.is_absolute() else Path(root) / rel


def episode_slug(season: int, episode: int) -> str:
    return f"S{season} E{episode}"


def parse_slug(name: str) -> tuple[int, int] | None:
    m = re.fullmatch(r"S(\d+)\s*E(\d+)", name.strip(), re.I)
    return (int(m[1]), int(m[2])) if m else None


class EpisodePaths:
    """Ordnerstruktur pro Folge (Heft §7)."""

    def __init__(self, settings: Settings, season: int, episode: int):
        self.settings = settings
        self.slug = episode_slug(season, episode)
        self.root = Path(settings.onedrive_root)
        self.base = self.root / settings.episodes_dir / self.slug
        self.gl = self.base / "glorfindel"
        self.scenes = self.gl / "szenen"
        self.maps = self.gl / "karten"
        self.assets = self.gl / "assets"
        self.recording = self.gl / "aufnahme"
        self.stills = self.base / "Videoelemente"
        self.locks = self.gl / "sperren"

    def ensure(self) -> None:
        for d in (self.scenes, self.maps, self.assets, self.recording, self.stills, self.locks):
            d.mkdir(parents=True, exist_ok=True)

    def cache(self) -> Path:
        d = app_dir() / "cache" / self.slug.replace(" ", "_")
        d.mkdir(parents=True, exist_ok=True)
        return d

    def work(self) -> Path:
        """Arbeitsdateien, die alle Rechner brauchen (Proxys, Szenenvorschläge, Vorschaubilder, Wellenformen).

        Standard: `<Folge>/glorfindel/arbeit` in OneDrive, damit andere Rechner sie direkt vorfinden.
        Ohne `share_work_files` bleibt alles im lokalen Cache. Ältere lokale Dateien werden einmal übernommen.
        """
        if not self.settings.share_work_files:
            return self.cache()
        d = self.gl / "arbeit"
        d.mkdir(parents=True, exist_ok=True)
        self._adopt_local(d)
        return d

    _adopted: set[str] = set()

    def _adopt_local(self, d: Path) -> None:
        key = str(d)
        if key in EpisodePaths._adopted:
            return
        EpisodePaths._adopted.add(key)
        local = self.cache()
        for src in [*local.glob("proxy_*.mp4"), local / "board.json", local / "thumbs", *local.glob("wave_*.json")]:
            dst = d / src.name
            if src.exists() and not dst.exists():
                try:
                    if src.is_dir():
                        shutil.copytree(src, dst)
                        shutil.rmtree(src, ignore_errors=True)
                    else:
                        tmp = dst.with_name(dst.name + ".part")
                        shutil.copy2(src, tmp)
                        tmp.replace(dst)
                        src.unlink(missing_ok=True)
                except OSError:
                    pass
