"""Folgen-Dienst: alle Lese-/Schreibvorgänge einer Folge auf der OneDrive-Ablage."""
from __future__ import annotations

import re
from pathlib import Path

from . import media, store
from .config import Settings
from .models import Anchor, Project, Scene, Source, Strand
from .paths import EpisodePaths, parse_slug, to_abs, to_rel

DEFAULT_STRANDS = [
    ("eregion", "Eregion", "#c0392b"), ("numenor", "Númenor", "#2980b9"),
    ("rhun", "Rhûn", "#d68910"), ("khazaddum", "Khazad-dûm", "#7d6608"),
]


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
        ep = cls(settings, season, episode)
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

    def import_source(self, path: str | Path, role: str = "screener", wait: bool = False) -> Source:
        """Quelle registrieren (Pfad relativ zum OneDrive-Stamm). Erste Quelle wird Referenz."""
        path = Path(path)
        if not path.is_absolute():
            path = to_abs(self.p.root, str(path))
        if wait:
            media.wait_until_stable(path)
        if media.is_online_only(path):
            raise RuntimeError("Datei liegt nur online (OneDrive). Ordner auf „Immer auf diesem Gerät behalten“ stellen.")
        info = media.probe(path)
        srcs = self.sources()
        rel = to_rel(self.p.root, path)
        existing = next((s for s in srcs if s.path == rel), None)
        sid = existing.id if existing else f"q{len(srcs) + 1}"
        src = Source(id=sid, path=rel, role=("referenz" if not srcs else role),  # type: ignore[arg-type]
                     duration=info["duration"], fps=info["fps"], width=info["width"], height=info["height"],
                     fingerprint=media.fingerprint(path), anchors=existing.anchors if existing else [])
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

    def ensure_proxy(self, sid: str) -> Path:
        dst = self.proxy_path(sid)
        if not dst.exists():
            s = self.source(sid)
            media.make_proxy(self.source_path(s), dst, crop=s.crop, fps=s.normalize_fps)
        return dst

    # ---- Szenen ----
    def scenes(self) -> list[Scene]:
        out = []
        for f in sorted(self.p.scenes.glob("sz_*.json")):
            if store._CONFLICT_RE.match(f.name) and (f.with_name(store._CONFLICT_RE.match(f.name)["stem"] + ".json")).exists():
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
        nums = [int(m[1]) for f in self.p.scenes.glob("sz_*.json") if (m := re.match(r"sz_(\d+)", f.name))]
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
        (self.p.scenes / f"{sid}.json").unlink(missing_ok=True)
        store.log_change(self.p.gl, self.settings.user, f"Szene {sid} gelöscht")

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
