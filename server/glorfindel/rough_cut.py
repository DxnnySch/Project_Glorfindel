"""Rohschnitt-Generator (Heft §5.8): baut das Schnittpaket `schnitt.json` im Spurlayout von S2 E7.

Reine Funktionen ohne Dateizugriff (außer `write_*`), damit alles testbar ist. Zeiten in Sekunden der
Hauptsequenz (auf deren Bildraster gerastet), Quellzeiten in Episodenzeit.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .config import Thresholds
from .models import CommentBlock, Scene
from .scenes import segment_of, still_plan, segment_light, speech_duration

DEFAULT_TEMPLATE_PATH = Path(__file__).resolve().parents[2] / "vorlagen" / "rohschnitt_vorlage.json"


def load_template(path: Path | None = None) -> dict:
    return json.loads((path or DEFAULT_TEMPLATE_PATH).read_text(encoding="utf-8"))


def credit_text(rule: str, artist: str, lowercase: bool = True) -> str:
    text = rule.replace("{kuenstler}", artist)
    return text.lower() if lowercase else text


def credit_from_filename(path: str) -> str:
    """Künstlername aus dem Dateinamen vorbelegen („Alan Lee - Bild 3.jpg“ -> „alan lee“)."""
    stem = Path(path).stem
    stem = re.sub(r"[\s_-]*\(?\d+\)?$", "", stem)       # Zählsuffix
    stem = re.split(r"\s+[-–]\s+", stem)[0]            # Titel nach Bindestrich abschneiden
    if " " in stem and "_" in stem:                      # „Ted Nasmith_Armenelos“: Unterstrich trennt Werktitel
        stem = stem.split("_")[0]
    return re.sub(r"_+", " ", stem).strip().lower()


class Timeline:
    def __init__(self, fps: float):
        self.fps = fps
        self.tracks: dict[str, list[dict]] = {}
        self.markers: list[dict] = []
        self.warnings: list[str] = []

    def snap(self, t: float) -> float:
        return round(t * self.fps) / self.fps

    def add(self, track: str, kind: str, start: float, end: float, **kw: Any) -> dict:
        clip = {"type": kind, "start": self.snap(start), "end": self.snap(end), **kw}
        if clip["end"] <= clip["start"]:
            clip["end"] = clip["start"] + 1.0 / self.fps
        self.tracks.setdefault(track, []).append(clip)
        return clip

    def mark(self, t: float, text: str, kind: str = "scene") -> None:
        self.markers.append({"time": self.snap(t), "text": text, "kind": kind})


def block_timing(block: CommentBlock, align: dict | None, th: Thresholds) -> tuple[float, list[float]]:
    """Dauer eines Kommentarblocks und Startzeit jeder Einheit (Wort bzw. Stichpunkt) relativ zum Blockanfang.

    Mit Abgleich: echte Zeiten aus der Aufnahme. Ohne: Schätzung (Sprechtempo bzw. Zeit pro Stichpunkt).
    """
    if block.modus == "stichpunkte":
        n = len(block.stichpunkte)
        if align and align.get("stichpunkte"):
            t0 = align["in"]
            by_i = {b["idx"]: b for b in align["stichpunkte"]}
            starts, last = [], 0.0
            for i in range(n):
                b = by_i.get(i)
                last = (b["in"] - t0) if b else last
                starts.append(max(0.0, last))
            return max(align["out"] - align["in"], 0.1), starts
        return n * th.bullet_seconds, [i * th.bullet_seconds for i in range(n)]
    n = len(block.text.split())
    if align and align.get("words"):
        t0 = align["in"]
        by_i = {w["i"]: w for w in align["words"]}
        starts, last = [], 0.0
        for i in range(n):
            w = by_i.get(i)
            last = (w["start"] - t0) if w else last
            starts.append(max(0.0, last))
        return max(align["out"] - align["in"], 0.1), starts
    dur = speech_duration(block.text, th)
    per = dur / n if n else 0
    return dur, [i * per for i in range(n)]


def block_unit(block: CommentBlock) -> str:
    return "stichpunkt" if block.modus == "stichpunkte" else "wort"


def build_package(scenes: list[Scene], *, slug: str, template: dict, th: Thresholds,
                  alignment: dict | None = None, assets: dict[str, dict] | None = None,
                  maps: dict[str, dict] | None = None, free_blocks: list[dict] | None = None,
                  still_names: dict[str, str] | None = None, version: int = 1,
                  episode_fps: float = 23.976, speaker_filter: set[str] | None = None) -> dict:
    seq = template["sequence"]
    tm, tr = template["timing"], template["tracks"]
    tl = Timeline(seq["fps"])
    assets, maps = assets or {}, maps or {}
    align_scenes = (alignment or {}).get("scenes", {})
    free_after: dict[str | None, list[dict]] = {}
    for fb in free_blocks or []:
        free_after.setdefault(fb.get("after"), []).append(fb)
    art_free_at = {t: 0.0 for t in tr["art"]}  # Belegung der Artwork-Spuren
    t = 0.0

    def place_free(key):
        nonlocal t
        for fb in free_after.get(key, []):
            dur = float(fb["dauer"]) if fb.get("dauer") else max(tm["free_block_min"], len((fb.get("text") or "").split()) / th.words_per_second)
            tl.mark(t, f"Freier Block: {fb.get('titel') or 'ohne Titel'}", "free")
            tl.add("GAP", "free_block", t, t + dur, title=fb.get("titel", ""), text=fb.get("text", ""))
            t += dur

    place_free(None)
    still_k = 0

    def place_still(sc, n, still_name, blocks, last_of_scene, amazon_clip):
        """Standbild nach einem Segment: Pause-Animation, Kommentarblöcke dieses Segments, Artworks/Karten."""
        nonlocal t
        sc_align = align_scenes.get(sc.id, [])
        offset = tm["comment_lead_in"]
        timings = []   # (block_idx, block, start_offset, dur, word_starts, alignment)
        for bi, block in blocks:
            if speaker_filter and block.sprecher not in speaker_filter:
                continue
            al = next((a for a in sc_align if a.get("block") == bi), None)
            if al and (al.get("missing") or al.get("in") is None or al.get("out") is None):
                al = None  # nicht gefunden -> Schätzung
            dur, starts = block_timing(block, al, th)
            timings.append((bi, block, offset, dur, starts, al))
            offset += dur + tm["block_gap"]
        comment_len = (offset - tm["block_gap"] + tm["comment_tail"]) if timings else 0.0
        still_len = max(tm["min_still"], comment_len)
        still_start, still_end = t, t + still_len
        still_clip = tl.add(tr["series_video"], "still", still_start, still_end, scene=sc.id, file=f"Videoelemente/{still_name}" if still_name else "")
        tl.add(tr["anim"], "anim", still_start - tm["pause_lead"], still_start - tm["pause_lead"] + tm["anim_len"], name="Pause", scene=sc.id)
        art_end_all = still_start
        for bi, block, off, dur, starts, al in timings:
            track = tr["speaker_audio"][block.sprecher]
            b_start = still_start + off
            clip = {"scene": sc.id, "block": bi, "speaker": block.sprecher, "text": block.text[:80]}
            if al:
                clip.update(rec=al.get("rec"), src_in=al["in"], src_out=al["out"])
            else:
                clip["placeholder"] = True
            tl.add(track, "comment", b_start, b_start + dur, **clip)
            if not al:
                tl.warnings.append(f"{sc.titel or sc.id} [{sc.id}], Block {bi + 1}: noch keine Aufnahme zugeordnet (Schätzung)")
            # ---- Anker: Artworks / Karten ----
            pending = [a for a in block.anker]
            for a in pending:
                ident = a.asset or a.karte
                a_start = b_start + (starts[a.von] if a.von < len(starts) else dur)
                if a.bis is None or a.einheit != block_unit(block):
                    a_end = b_start + dur
                else:
                    a_end = b_start + (starts[a.bis] if a.bis < len(starts) else dur)
                a_end = max(a_end, a_start + tm["min_artwork"])
                tl.mark(a_start, f"{'Karte' if a.karte else 'Bild'}: {ident}", "map" if a.karte else "asset")
                if a.karte:
                    mp = maps.get(a.karte, {})
                    hint = (mp.get("hinweise") or "").strip()
                    if hint:
                        tl.markers[-1]["text"] += f" – {hint}"
                    track_a = _pick_track(art_free_at, a_start, a_end)
                    tl.add(track_a, "map_placeholder", a_start, a_end, ref=a.karte, scene=sc.id,
                           file=mp.get("placeholder_clip", ""),
                           effects=[{"recipe": "karte_in"}, {"recipe": "karte_out"}])
                    art_end_all = max(art_end_all, a_end)
                    continue
                asset = assets.get(ident)
                if asset is None:
                    tl.warnings.append(f"{sc.titel or sc.id} [{sc.id}]: Asset {ident} fehlt in der Bibliothek")
                    asset = {}
                if a.layout == "doppel_links":
                    track_a = tr["art"][0]
                elif a.layout == "doppel_rechts":
                    track_a = tr["art"][1]
                else:
                    track_a = _pick_track(art_free_at, a_start, a_end, tl, sc.id)
                art_free_at[track_a] = max(art_free_at.get(track_a, 0), a_end)
                contour = asset.get("contour_color") or "#752416"
                effects = [{"recipe": "fancy_in", "contour": contour}, {"recipe": "zoom_1_0"},
                           {"recipe": "fancy_out", "contour": contour}, {"recipe": "drop_shadow"}]
                art = tl.add(track_a, "artwork", a_start, a_end, ref=ident, scene=sc.id, file=asset.get("path", ""),
                             mask="Maske Quadrat.png", layout=a.layout, effects=effects,
                             **({"position": template["doppelbild"]["links" if a.layout == "doppel_links" else "rechts"]}
                                if a.layout != "einzel" else {}))
                # Credit exakt so lang wie das Artwork
                artist = asset.get("credit") or credit_from_filename(asset.get("path", ident))
                if not asset.get("credit"):
                    tl.warnings.append(f"{sc.titel or sc.id} [{sc.id}]: Credit für {ident} aus Dateiname vorbelegt („{artist}“)")
                credit_track = tr["credit_artwork"][1 if a.layout == "doppel_rechts" else 0]
                tl.add(credit_track, "credit", a_start, a_end, slot="credit_artwork",
                       text=credit_text("© {kuenstler}", artist), scene=sc.id, over=track_a,
                       fade=tm["artwork_fade"], anchor_to="top_center_of_image")
                # Blur-Einstellungsebene: Gauß In, dann Rest bis Artwork-Ende
                bin_end = min(a_start + tm["blur_in"], a_end)
                tl.add(tr["blur"], "blur", a_start, bin_end, scene=sc.id, effects=[{"recipe": "gauss_in"}])
                if a_end - bin_end > 1.0 / tl.fps:
                    tl.add(tr["blur"], "blur", bin_end, a_end, scene=sc.id, effects=[{"recipe": "gauss_const"}])
                art_end_all = max(art_end_all, a_end)
        # Standbild muss alle Artworks tragen
        if art_end_all > still_end:
            extra = art_end_all - still_end
            still_clip["end"] = tl.snap(art_end_all)
            still_end = tl.snap(art_end_all)
            tl.warnings.append(f"{sc.titel or sc.id} [{sc.id}]: Standbild um {extra:.1f} s verlängert (Artwork ragte über)")
        t = still_end
        amazon_clip["end"] = max(amazon_clip["end"], still_end)
        return still_end

    for n, sc in enumerate(scenes, 1):
        # ---- Serienmaterial ----
        s_start = t
        if not sc.segmente:
            tl.warnings.append(f"{sc.titel or sc.id}: noch kein Serienmaterial (Segment) gesetzt")
        tl.mark(t, f"Szene {n:02d}: {sc.titel or sc.id}" + (f" [{sc.strang}]" if sc.strang else ""))
        amazon_clip = tl.add(tr["credit_amazon"], "credit", s_start, s_start, slot="credit_amazon", text="© amazon studios", scene=sc.id)
        plan = set(still_plan(sc))
        by_seg: dict[int, list] = {}
        for bi, block in enumerate(sc.kommentar):
            by_seg.setdefault(segment_of(block, sc), []).append((bi, block))
        last_still = False
        for i, seg in enumerate(sc.segmente):
            if segment_light(seg.duration, th) == "rot":
                tl.warnings.append(f"{sc.titel or sc.id} [{sc.id}]: Segment {i + 1} ist {seg.duration:.1f} s lang (> {th.max_segment_s} s)")
            dur = seg.duration
            tl.add(tr["series_video"], "scene_segment", t, t + dur, scene=sc.id, src="episode",
                   src_in=seg.in_, src_out=seg.out, **({"note": seg.notiz} if seg.notiz else {}))
            tl.add(tr["series_audio"], "scene_audio", t, t + dur, scene=sc.id, src="episode",
                   src_in=seg.in_, src_out=seg.out,
                   effects=[{"recipe": "const_power", "edge": "both", "duration": tm["audio_crossfade"]}])
            t += dur
            amazon_clip["end"] = t
            if i in plan:
                still_k += 1
                last_still = place_still(sc, n, f"{still_k}.png", by_seg.get(i, []), i == len(sc.segmente) - 1, amazon_clip) is not None
        if not sc.segmente and sc.standbild != "aus":      # Szene ohne Material: Platzhalter-Standbild für Kommentare
            place_still(sc, n, "", by_seg.get(0, []), True, amazon_clip)
            last_still = True
        # Play-Animation vor der nächsten Szene
        if n < len(scenes) and last_still:
            tl.add(tr["anim"], "anim", t - tm["play_lead"], t - tm["play_lead"] + tm["anim_len"], name="Play", scene=sc.id)
        place_free(sc.id)

    media = sorted({c.get("file") for cl in tl.tracks.values() for c in cl if c.get("file")})
    return {
        "version": version,
        "schema_version": 1,
        "sequence": {**seq, "name": f"{template['sequence']['name']} {slug} v{version}"},
        "episode_sequence": template["episode_sequence_name"].format(slug=slug),
        "episode_fps": episode_fps,
        "media": media,
        "tracks": tl.tracks,
        "markers": sorted(tl.markers, key=lambda m: m["time"]),
        "duration": t,
        "warnings": tl.warnings,
    }


def _pick_track(free_at: dict[str, float], start: float, end: float, tl: Timeline | None = None,
                scene: str = "") -> str:
    """Überlappende Artworks wechseln zwischen V3 und V4: erste freie Spur, sonst die früher freiwerdende."""
    for tk, fa in free_at.items():
        if fa <= start + 1e-6:
            free_at[tk] = end
            return tk
    tk = min(free_at, key=free_at.get)
    if tl:
        tl.warnings.append(f"{scene}: Artworks überlappen auf beiden Spuren")
    free_at[tk] = end
    return tk


def write_package(pkg: dict, folder: Path) -> Path:
    """Schreibt `schnitt_vN.json` (Neu-Generieren überschreibt nie eine ältere Version)."""
    folder.mkdir(parents=True, exist_ok=True)
    p = folder / f"schnitt_v{pkg['version']}.json"
    p.write_text(json.dumps(pkg, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def next_version(folder: Path) -> int:
    nums = [int(m[1]) for f in folder.glob("schnitt_v*.json") if (m := re.match(r"schnitt_v(\d+)\.json", f.name))]
    return max(nums, default=0) + 1
