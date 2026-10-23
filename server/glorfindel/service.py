"""Folgen-Dienst: alle Lese-/Schreibvorgänge einer Folge auf der OneDrive-Ablage."""
from __future__ import annotations

import re
import shutil
import time
import threading
from pathlib import Path

from . import media, store
from .config import Settings
from .models import Anchor, Project, Scene, Source, Strand
from .paths import EpisodePaths, parse_slug, to_abs, to_rel

DEFAULT_STRANDS = [
    ("eregion", "Eregion", "#c0392b"), ("numenor", "Númenor", "#2980b9"),
    ("rhun", "Rhûn", "#d68910"), ("khazaddum", "Khazad-dûm", "#7d6608"),
]

_PROXY_LOCKS: dict[str, threading.Lock] = {}


def list_episodes(settings: Settings) -> list[dict]:
    base = Path(settings.onedrive_root) / settings.episodes_dir
    out = []
    if base.is_dir():
        for d in sorted(base.iterdir()):
            se = parse_slug(d.name)
            if se and (d / "glorfindel" / "projekt.json").exists():
                data = store.read_json(d / "glorfindel" / "projekt.json", {})
                out.append({"season": se[0], "episode": se[1], "title": data.get("title", "")})
    return out


class Episode:
    def __init__(self, settings: Settings, season: int, episode: int):
        self.settings = settings
        self.p = EpisodePaths(settings, season, episode)
        self.season, self.episode = season, episode

    # ---- Projekt ----
    @classmethod
    def create(cls, settings: Settings, season: int, episode: int, title: str = "", fps: float = 23.976) -> "Episode":
        if not (1 <= season <= 99 and 1 <= episode <= 999):
            raise ValueError("Staffel 1–99 und Folge 1–999 angeben.")
        ep = cls(settings, season, episode)
        if ep.exists():
            raise FileExistsError(f"S{season} E{episode} gibt es schon.")
        ep.p.ensure()
        if not (ep.p.gl / "projekt.json").exists():
            store.write_json(ep.p.gl / "projekt.json", Project(season=season, episode=episode, title=title, fps=fps).model_dump())
            store.write_json(ep.p.gl / "quellen.json", [])
            store.write_json(ep.p.gl / "straenge.json", [
                Strand(id=i, name=n, color=c, order=k).model_dump() for k, (i, n, c) in enumerate(DEFAULT_STRANDS)])
            store.log_change(ep.p.gl, settings.user, "Projekt angelegt")
        return ep

    def exists(self) -> bool:
        return (self.p.gl / "projekt.json").exists()

    def project(self) -> Project:
        return Project.model_validate(store.read_json(self.p.gl / "projekt.json"))

    def save_project(self, pr: Project) -> None:
        store.write_json(self.p.gl / "projekt.json", pr.model_dump())

    # ---- Quellen ----
    def sources(self) -> list[Source]:
        return [Source.model_validate(s) for s in store.read_json(self.p.gl / "quellen.json", [])]

    def _save_sources(self, srcs: list[Source]) -> None:
        store.write_json(self.p.gl / "quellen.json", [s.model_dump() for s in srcs])

    def source(self, sid: str) -> Source:
        for s in self.sources():
            if s.id == sid:
                return s
        raise KeyError(sid)

    def source_path(self, s: Source) -> Path:
        return to_abs(self.p.root, s.path)

    def import_source(self, path: str | Path, role: str = "screener", wait: bool = False, progress=None) -> Source:
        """Quelle registrieren (Pfad relativ zum OneDrive-Stamm). Erste Quelle wird Referenz."""
        path = Path(path)
        if not path.is_absolute():
            path = to_abs(self.p.root, str(path))
        if not path.is_file():
            raise FileNotFoundError(f"Datei nicht gefunden: {path}")
        from .progress import as_progress
        pr_ = as_progress(progress)
        pr_.plan([("Datei prüfen (vollständig synchronisiert?)", 2), ("Metadaten lesen (Länge, Bildrate, Auflösung)", 1), ("Audio-Fingerabdruck berechnen", 3), ("In das Projekt eintragen", 1)])
        pr_.step(0, "Warte, bis die Dateigröße stabil ist")
        if wait:
            media.wait_until_stable(path, on_check=lambda n, total, size: pr_.sub(n, total, f"Dateigröße {size / 1e6:,.0f} MB unverändert".replace(",", "."), "Prüfungen"))
        if media.is_online_only(path):
            raise RuntimeError("Datei liegt nur online (OneDrive). Ordner auf „Immer auf diesem Gerät behalten“ stellen.")
        pr_.step(1, path.name)
        info = media.probe(path)
        pr_.step(2, f"Erste Sekunden von {path.name} auswerten")
        srcs = self.sources()
        rel = to_rel(self.p.root, path)
        existing = next((s for s in srcs if s.path == rel), None)
        sid = existing.id if existing else f"q{len(srcs) + 1}"
        src = Source(id=sid, path=rel, role=(existing.role if existing else "referenz" if not srcs else role),  # type: ignore[arg-type]
                     duration=info["duration"], fps=info["fps"], width=info["width"], height=info["height"],
                     fingerprint=media.fingerprint(path), anchors=existing.anchors if existing else [])
        pr_.step(3, f"Quelle {sid} speichern")
        srcs = [s for s in srcs if s.id != sid] + [src]
        self._save_sources(sorted(srcs, key=lambda s: s.id))
        pr = self.project()
        if not pr.reference_source:
            pr.reference_source = sid
            self.save_project(pr)
        store.log_change(self.p.gl, self.settings.user, f"Quelle {sid} importiert ({rel})")
        return src

    def relocate_source(self, sid: str) -> Source | None:
        """Datei verschoben/umbenannt? Suche per Audio-Fingerabdruck im Episodenordner."""
        s = self.source(sid)
        if self.source_path(s).exists() or not s.fingerprint:
            return s
        for cand in self.p.base.parent.rglob("*"):
            if cand.suffix.lower() in {".mp4", ".mov", ".mkv"} and media.fingerprint(cand) == s.fingerprint:
                s.path = to_rel(self.p.root, cand)
                srcs = [x for x in self.sources() if x.id != sid] + [s]
                self._save_sources(srcs)
                return s
        return None

    def set_anchors(self, sid: str, anchors: list[Anchor]) -> Source:
        srcs = self.sources()
        for s in srcs:
            if s.id == sid:
                s.anchors = sorted(anchors, key=lambda a: a.ref)
                self._save_sources(srcs)
                store.log_change(self.p.gl, self.settings.user, f"Anker für {sid}: {len(anchors)}")
                return s
        raise KeyError(sid)

    def proxy_path(self, sid: str) -> Path:
        return self.p.cache() / f"proxy_{sid}.mp4"

    def ensure_proxy(self, sid: str, on_progress=None) -> Path:
        dst = self.proxy_path(sid)
        with _PROXY_LOCKS.setdefault(str(dst), threading.Lock()):  # Auto-Proxy und manueller Auftrag nie gleichzeitig
            if not dst.exists():
                s = self.source(sid)
                media.make_proxy(self.source_path(s), dst, crop=s.crop, fps=s.normalize_fps, on_progress=on_progress)
        return dst

    # ---- Szenen ----
    def scenes(self) -> list[Scene]:
        out = []
        for f in sorted(self.p.scenes.glob("sz_*.json")):
            if store.conflict_original(f):
                continue  # Konfliktkopie, nicht als Szene laden
            try:
                out.append(Scene.model_validate(store.read_json(f)))
            except Exception:
                continue
        return sorted(out, key=lambda s: (s.reihenfolge, s.id))

    def scene(self, sid: str) -> Scene:
        data = store.read_json(self.p.scenes / f"{sid}.json")
        if data is None:
            raise KeyError(sid)
        return Scene.model_validate(data)

    def next_scene_id(self) -> str:
        files = list(self.p.scenes.glob("sz_*.json")) + list((self.p.gl / "papierkorb").glob("sz_*.json"))
        nums = [int(m[1]) for f in files if (m := re.match(r"sz_(\d+)", f.name))]
        return f"sz_{(max(nums) + 1) if nums else 1:02d}"

    def save_scene(self, sc: Scene, what: str = "") -> Scene:
        sc.geaendert_von = self.settings.user
        sc.geaendert_am = store.now_iso()
        store.write_json(self.p.scenes / f"{sc.id}.json", sc.model_dump(by_alias=True))
        store.log_change(self.p.gl, self.settings.user, what or f"Szene {sc.id} gespeichert")
        return sc

    def create_scene(self, **kw) -> Scene:
        sc = Scene(id=self.next_scene_id(), reihenfolge=len(self.scenes()), **kw)
        return self.save_scene(sc, f"Szene {sc.id} angelegt")

    def delete_scene(self, sid: str) -> None:
        f = self.p.scenes / f"{sid}.json"
        if f.exists():
            trash = self.p.gl / "papierkorb"
            trash.mkdir(parents=True, exist_ok=True)
            dst = trash / f"{sid}.json"
            if dst.exists():
                dst = trash / f"{sid}_{int(time.time())}.json"
            shutil.move(str(f), str(dst))
        remaining = [s.id for s in self.scenes()]
        blocks = self.free_blocks()
        if any(b.get("after") == sid for b in blocks):  # Rahmenteile wandern zur vorherigen Szene
            prev = next((x for x in reversed(sorted(remaining)) if x < sid), None)
            for b in blocks:
                if b.get("after") == sid:
                    b["after"] = prev
            self.save_free_blocks(blocks)
        store.log_change(self.p.gl, self.settings.user, f"Szene {sid} gelöscht")

    def restore_scene(self, sid: str) -> Scene:
        src = self.p.gl / "papierkorb" / f"{sid}.json"
        if not src.exists():
            raise FileNotFoundError("Nicht im Papierkorb")
        dst = self.p.scenes / f"{sid}.json"
        if dst.exists():
            raise FileExistsError("Szene existiert bereits")
        shutil.move(str(src), str(dst))
        store.log_change(self.p.gl, self.settings.user, f"Szene {sid} wiederhergestellt")
        return Scene.model_validate(store.read_json(dst))

    def renumber(self, ordered_ids: list[str]) -> None:
        for i, sid in enumerate(ordered_ids):
            sc = self.scene(sid)
            if sc.reihenfolge != i:
                sc.reihenfolge = i
                self.save_scene(sc, f"Reihenfolge {sid}")

    # ---- Stränge ----
    def strands(self) -> list[Strand]:
        return [Strand.model_validate(s) for s in store.read_json(self.p.gl / "straenge.json", [])]

    def save_strands(self, strands: list[Strand]) -> None:
        store.write_json(self.p.gl / "straenge.json", [s.model_dump() for s in strands])

    # ---- Freie Blöcke (aus Word-Rückimport) ----
    def free_blocks(self) -> list[dict]:
        return store.read_json(self.p.gl / "freie_bloecke.json", [])

    def save_free_blocks(self, blocks: list[dict]) -> None:
        store.write_json(self.p.gl / "freie_bloecke.json", blocks)
