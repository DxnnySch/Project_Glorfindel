"""Lokale Einstellungen (pro Rechner, nie in OneDrive/Repo)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from pydantic import BaseModel, Field

SCHEMA_VERSION = 1


def app_dir() -> Path:
    """Lokaler, nicht synchronisierter Ordner für Einstellungen, Proxys, Caches."""
    override = os.environ.get("GLORFINDEL_HOME")
    if override:
        p = Path(override)
    elif sys.platform == "win32":
        p = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "Glorfindel"
    elif sys.platform == "darwin":
        p = Path.home() / "Library/Caches/Glorfindel"
    else:
        p = Path.home() / ".cache/glorfindel"
    p.mkdir(parents=True, exist_ok=True)
    return p


class LlmSettings(BaseModel):
    enabled: bool = True
    base_url: str = "https://llm.scads.ai/v1"
    models: dict[str, str] = Field(default_factory=dict)  # Funktion -> Modell; leer = automatisch
    features: dict[str, bool] = Field(default_factory=lambda: {
        "transcript_fix": True, "name_check": True, "image_suggest": True,
        "map_suggest": True, "scene_titles": True,
    })


class Thresholds(BaseModel):
    max_segment_s: float = 9.5
    warn_ratio: float = 0.8
    target_series_share: float = 0.34
    words_per_second: float = 2.6  # Sprechtempo Deutsch für die Dauerschätzung


class Settings(BaseModel):
    user: str = "danny"
    onedrive_root: str = ""
    episodes_dir: str = "Mythen-Archiv/Videos"
    images_dirs: list[str] = Field(default_factory=lambda: ["Videomaterial/Bilder"])
    maps_dir: str = "Videomaterial/Karten"
    templates_dir: str = "Videomaterial/Project_Glorfindel"
    whisper_model: str = "auto"
    thresholds: Thresholds = Field(default_factory=Thresholds)
    llm: LlmSettings = Field(default_factory=LlmSettings)
    keep_hq_in_onedrive: bool = False


def settings_path() -> Path:
    return app_dir() / "settings.json"


def load_settings() -> Settings:
    p = settings_path()
    if p.exists():
        try:
            return Settings.model_validate_json(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return Settings()


def save_settings(s: Settings) -> None:
    settings_path().write_text(s.model_dump_json(indent=2), encoding="utf-8")


def scads_credentials() -> tuple[str, str]:
    """API-Schlüssel nur aus Umgebung/.env (lokal)."""
    from dotenv import load_dotenv

    for cand in (Path.cwd() / ".env", Path(__file__).resolve().parents[2] / ".env", app_dir() / ".env"):
        if cand.exists():
            load_dotenv(cand, override=False)
    return os.environ.get("SCADS_API_KEY", ""), os.environ.get("SCADS_BASE_URL", "https://llm.scads.ai/v1")
