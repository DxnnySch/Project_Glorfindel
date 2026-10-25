"""Datenmodelle (Schema-Version für Migrationen)."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from .config import SCHEMA_VERSION

Speaker = Literal["philipp", "danny"]
SceneStatus = Literal["neu", "skript_fertig", "aufgenommen", "abgeglichen", "veraltet"]
SourceRole = Literal["referenz", "screener", "hq", "screencapture"]


class Segment(BaseModel):
    in_: float = Field(alias="in")
    out: float
    notiz: str = ""  # eigener Kontext zusätzlich zum automatischen Dialog
    model_config = {"populate_by_name": True}

    @property
    def duration(self) -> float:
        return max(0.0, self.out - self.in_)


class Anchor(BaseModel):
    ref: float  # Episodenzeit (s)
    src: float  # Zeit in der Quelle (s)


class AssetRef(BaseModel):
    asset: Optional[str] = None
    karte: Optional[str] = None
    von: int = 0               # Wortindex
    bis: Optional[int] = None  # None = bis Ende des Kommentars
    layout: Literal["einzel", "doppel_links", "doppel_rechts"] = "einzel"
    einheit: Literal["wort", "stichpunkt"] = "wort"  # von/bis zählen Wörter oder Stichpunkte


class CommentBlock(BaseModel):
    sprecher: Speaker = "philipp"
    modus: Literal["text", "stichpunkte"] = "text"  # Stichpunkte: wird frei ausformuliert gesprochen
    text: str = ""          # reiner Sprechtext (Wortzählung, Abgleich, Anker)
    markup: str = ""        # formatierte Fassung (kleines Markdown); leer = nicht formatiert. Wenn gesetzt, ist `text` = plain(markup)
    stichpunkte: list[str] = Field(default_factory=list)
    gesprochen: str = ""  # nach dem Abgleich: tatsächlich gesprochener Text (Transkript)
    anker: list[AssetRef] = Field(default_factory=list)
    segment: Optional[int] = None  # Index des Segments, zu dem der Kommentar gehört; None = letztes Segment


class Scene(BaseModel):
    schema_version: int = SCHEMA_VERSION
    id: str
    strang: str = ""
    reihenfolge: int = 0
    titel: str = ""
    segmente: list[Segment] = Field(default_factory=list)
    bereich: Optional[list[float]] = None  # [Start, Ende] der Szene in der Referenz (Board)
    standbild: Literal["ende", "start", "aus"] = "ende"
    kommentar: list[CommentBlock] = Field(default_factory=list)
    fixiert: bool = False  # "dramaturgisch fixieren"
    status: SceneStatus = "neu"
    geaendert_von: str = ""
    geaendert_am: str = ""


class Source(BaseModel):
    id: str
    path: str  # relativ zum OneDrive-Stamm
    role: SourceRole = "screener"
    duration: float = 0.0
    fps: float = 0.0
    width: int = 0
    height: int = 0
    fingerprint: str = ""
    anchors: list[Anchor] = Field(default_factory=list)
    proxy: str = ""  # lokal, nicht synchronisiert
    crop: Optional[list[int]] = None  # [x, y, w, h] gegen Letterbox
    normalize_fps: Optional[float] = None  # Ziel-Bildrate bei variabler Bildrate


class Strand(BaseModel):
    id: str
    name: str
    color: str = "#888888"
    order: int = 0


class Project(BaseModel):
    schema_version: int = SCHEMA_VERSION
    season: int
    episode: int
    title: str = ""
    fps: float = 23.976
    reference_source: str = ""
    ablauf: list[str] = Field(default_factory=list)  # manuelle Gesamtreihenfolge der Szenen (leer = nach Strängen)
    dialog_sprache: str = "auto"
    einheiten_migriert: bool = False  # Szenen = Messeinheiten (Bereich), Segmente frei: Altdaten einmalig umgestellt
