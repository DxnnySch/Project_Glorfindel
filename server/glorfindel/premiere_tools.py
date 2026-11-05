"""Fachliche Seite der Panel-Werkzeuge (Kurzbefehle in Premiere).

Das Panel schickt eine Anfrage (`rpc`), dieses Modul trifft die Entscheidungen nach denselben Regeln wie der Rohschnitt-Bau
(Effektrezepte, Artwork mit Maske, Credit-Text und -Vorlage, Ton-Blenden, Szenen) und liefert dem Panel fertige Angaben.
Das Panel führt nur Premiere-Grundoperationen aus."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from . import autoframe, mogrt_text, store
from .config import app_dir
from .premiere_media import credit_png
from .rough_cut import credit_from_filename, credit_text

RPC_METHODS = {"tools.config", "tools.effects", "tools.artwork", "tools.credit", "tools.audiofade", "tools.scene_at"}

CONTOUR = "#752416"                                            # wie im Bau, wenn ein Artwork keine eigene Konturfarbe hat
CREDIT_TRACKS = {"amazon": 8, "artwork": 9, "musik": 10}       # V9, V10, V11 (Heft/DESIGN.md); 0-basiert
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp"}   # nur Bilder werden geöffnet (und ggf. an das Vision-Modell geschickt)
SOURCE_TRACKS = [2, 3, 0]                                     # wo die Bilder liegen, zu denen ein Credit gehört: Artwork V3/V4, dann Standbilder V1 (0-basiert)
CREDIT_NAMES = {"amazon": "Amazon", "artwork": "Künstler", "musik": "Musik"}
LABELS = {"karte": "Karte", "gauss": "Gauß", "pop": "Pop", "kreis": "Kreis", "fancy": "Fancy-Kante", "trans": "Transformieren", "right": "Von rechts",
          "zoom_schnell": "Zoom schnell", "zoom_langsam": "Zoom langsam", "drop_shadow": "Schlagschatten"}
ORDER = ["karte", "gauss", "zoom_schnell", "zoom_langsam", "pop", "kreis", "fancy", "trans", "right", "drop_shadow"]


@dataclass
class ToolContext:
    recipes: dict
    settings: dict
    masks: Path
    nested_preset: str
    credit_mogrt: dict
    artist_db: dict
    cache: Path
    frame_box: Callable[[Path], dict | None] | None = None
    plan: dict | None = None                                   # letzter Bauplan (für Szene am Abspielkopf)
    scenes: dict = field(default_factory=dict)                 # Szenen-ID -> {titel, status}
    calibration: dict = field(default_factory=dict)            # gemessene Eigenheiten der Premiere-API (Farbformat, Keyframe-Zeitbezug)


def _all_recipes(ctx: ToolContext) -> dict[str, dict]:
    out = {c["id"]: c for c in ctx.recipes.get("artwork_kette", [])}
    out.update(ctx.recipes.get("bibliothek", {}))
    return out


def config(ctx: ToolContext) -> dict:
    rec = _all_recipes(ctx)
    rows: dict[str, dict] = {}
    for rid in rec:
        if rid == "zoom":                                      # Alias von zoom_schnell
            continue
        base, kind = (rid[:-3], "ein") if rid.endswith("_in") else (rid[:-4], "aus") if rid.endswith("_out") else (rid, "einzel")
        row = rows.setdefault(base, {"id": base, "name": LABELS.get(base, base.replace("_", " ").title())})
        row[kind] = rid
    rank = lambda r: (ORDER.index(r["id"]) if r["id"] in ORDER else len(ORDER), r["id"])
    vd = (ctx.recipes.get("uebergaenge") or {}).get("video", {})
    ad = (ctx.recipes.get("uebergaenge") or {}).get("audio", {})
    return {"effekte": sorted(rows.values(), key=rank),
            "credits": [{"art": a, "name": CREDIT_NAMES[a], "vorlage": a in ctx.credit_mogrt, "track": t} for a, t in CREDIT_TRACKS.items()],
            "uebergang": {"match_name": vd.get("match_name", "AE.ADBE Cross Dissolve New"), "dauer": float(vd.get("dauer", 0.4167))},
            "ton": {"dauer": float(ad.get("dauer", 1.0)), "schnitt_dauer": float(ad.get("schnitt_dauer", 0.0))},
            "calibration": ctx.calibration, "quellspuren": SOURCE_TRACKS}


def effects(ctx: ToolContext, ids: list[str], clips: list[dict]) -> dict:
    """Rezepte für jeden Clip in Clip-Zeit auflösen (Keyframes ab Anfang bzw. relativ zum Ende, je nach Rezept)."""
    from .premiere_plan import _resolve_chain
    rec = _all_recipes(ctx)
    missing = [i for i in ids if i not in rec]
    if missing:
        raise ValueError("Effekt unbekannt: " + ", ".join(missing) + " (Bibliothek: " + ", ".join(sorted(rec)) + ")")
    fps = float(ctx.settings.get("fps", 24.0))
    return {"clips": [_resolve_chain(ctx.recipes, [{"recipe": i} for i in ids], float(c["dur"]), None, fps) for c in clips]}


def audiofade(ctx: ToolContext, dur: float, ein: float | None = None, aus: float | None = None) -> dict:
    from .premiere_plan import equal_power_keyframes
    d = float(((ctx.recipes.get("uebergaenge") or {}).get("audio") or {}).get("dauer", 1.0))
    return {"keyframes": equal_power_keyframes(float(dur), d if ein is None else float(ein), d if aus is None else float(aus))}


def _image_size(path: Path) -> tuple[int, int]:
    from PIL import Image
    with Image.open(path) as im:
        return im.size


def artwork(ctx: ToolContext, path: str, dur: float) -> dict:
    """Verschachtelte Artwork-Sequenz (Bild + Maske + Spurmaske) und Standardeffekte, wie sie der Bau für ein Einzelbild anlegt."""
    from .premiere_plan import _resolve_chain
    f = Path(path)
    if f.suffix.lower() not in IMAGE_SUFFIXES:
        raise ValueError(f"„{f.name}“ ist kein Bild (erlaubt: {', '.join(sorted(IMAGE_SUFFIXES))}); Artwork lässt sich nur aus Bildern bauen.")
    if not f.is_file():
        raise ValueError(f"Bild nicht gefunden: {f}")
    st = ctx.settings
    size = _image_size(f)
    mode = st.get("mask", "auto")
    mask = autoframe.pick_mask(size) if mode == "auto" else mode
    if mask not in autoframe.VISIBLE_PX or not (ctx.masks / mask).exists():
        raise ValueError(f"Maske „{mask}“ fehlt im Ordner {ctx.masks}")
    vw, vh = autoframe.VISIBLE_PX[mask]
    shown_w = float(st["art_px"]) * vw / vh if mask == "Maske Quadrat.png" else float(st["landscape_px"])
    box = ctx.frame_box(f) if ctx.frame_box else None
    fr = autoframe.frame_image(size, mask, shown_w, box, center=(0.5, 0.5))
    chain = _resolve_chain(ctx.recipes, [{"recipe": r} for r in st.get("artwork_effects", ("drop_shadow", "zoom", "fancy_out", "fancy_in"))],
                           float(dur), CONTOUR, float(st.get("fps", 24.0)))
    return {"nested": {"name": f"Artwork {f.stem}", "dur": float(dur), "image": str(f), "mask": str(ctx.masks / mask), "image_track": 2, "mask_track": 4,
                       "matte_track": 5, "image_scale": fr["image_scale"], "mask_scale": fr["mask_scale"], "image_position": fr["image_position"],
                       "mask_position": fr["mask_position"], "preset": ctx.nested_preset},
            "effects": chain}


def credit_text_for(ctx: ToolContext, path: str | None, name: str | None, text: str | None) -> str:
    """Credit-Text wie im Bau: frei eingegebener Text bleibt, sonst „© künstler“ aus Künstlerdatenbank bzw. Dateiname (Clipname)."""
    if text and text.strip():
        return text.strip()
    base = credit_from_filename(path or re.sub(r"^artwork\s+(\d+\s+)?", "", name or "", flags=re.I))
    if not base:
        raise ValueError("Kein Name für den Credit: Clip mit Bilddatei wählen oder Text eingeben. "
                         f"(Clip „{name or ''}“, Datei „{path or ''}“)")
    return credit_text("© {kuenstler}", ctx.artist_db.get(base, base))


def credit(ctx: ToolContext, art: str, path: str | None, name: str | None, text: str | None, dur: float) -> dict:
    if art not in CREDIT_TRACKS:
        raise ValueError(f"Credit-Art unbekannt: {art}")
    tpl = ctx.credit_mogrt.get(art)
    if not tpl:
        raise ValueError(f"Keine Credit-Vorlage für „{CREDIT_NAMES[art]}“: Datei „Credit {art.capitalize()}.mogrt“ in vorlagen/mogrt ablegen.")
    t = credit_text_for(ctx, path, name, text) if art != "amazon" or text or path or name else "© amazon studios"
    baked = mogrt_text.text_mogrt(Path(tpl), t, ctx.cache / "mogrt")
    vd = (ctx.recipes.get("uebergaenge") or {}).get("video", {})
    try:                                                       # Rückfall, falls Premiere die Grafik der Vorlage nicht lädt
        png = str(credit_png(t, art, ctx.cache / "credits"))
    except Exception:  # noqa: BLE001 – ohne PNG meldet das Panel den Fehler
        png = None
    return {"text": t, "art": art, "track": CREDIT_TRACKS[art], "mogrt": str(baked), "png": png, "dur": float(dur), "dx": 0.0,
            "uebergang": float(vd.get("dauer", 0.4167))}


def _clips_of(ctx: ToolContext, scene: str) -> list[dict]:
    return [c for c in (ctx.plan or {}).get("clips", []) if c.get("scene") == scene]


def scene_at(ctx: ToolContext, t: float) -> dict:
    """Szene an einer Zeit der gebauten Sequenz (Szene des Episodenclips dort, sonst eines beliebigen Clips mit Szene)."""
    if not ctx.plan:
        raise ValueError("Noch kein Rohschnitt gebaut: Szenen sind erst nach dem Bau bekannt.")
    at = [c for c in ctx.plan["clips"] if c.get("scene") and c["start"] <= t < c["end"]]
    hit = next((c for c in at if c["kind"] == "episode"), at[0] if at else None)
    if not hit:
        return {"scene": ""}
    sid = hit["scene"]
    cl = _clips_of(ctx, sid)
    meta = ctx.scenes.get(sid, {})
    return {"scene": sid, "titel": meta.get("titel", ""), "status": meta.get("status", ""),
            "start": min(c["start"] for c in cl), "end": max(c["end"] for c in cl)}


def scene_start(ctx: ToolContext, scene: str) -> float:
    cl = _clips_of(ctx, scene)
    if not cl:
        raise ValueError(f"Szene {scene} ist nicht im Rohschnitt (neu bauen).")
    return min(c["start"] for c in cl)


# ---------- Kontext aus der Folge ----------
def context_path() -> Path:
    return app_dir() / "bridge_context.json"


def remember_episode(ep) -> None:
    """Die zuletzt gebaute Folge merken: Das Panel weiß nicht, welche Folge zum geöffneten Projekt gehört."""
    store.write_json(context_path(), {"season": ep.season, "episode": ep.episode})


def build_context(ep, templates_dir: Path) -> ToolContext:
    from . import premiere_ops as ops
    from .premiere_plan import load_recipes, with_library
    from .premiere_preset import make_sequence_preset
    s = ep.settings.premiere
    recipes_file = templates_dir / "premiere_rezepte.json"
    recipes = with_library(load_recipes(recipes_file if recipes_file.exists() else None), ops._library(ep, templates_dir))
    pdir = ops.pdir(ep)
    nested = pdir / f"Glorfindel-Artwork-{s.sequence_fps:g}fps.sqpreset"
    if not nested.exists():
        make_sequence_preset(nested, video_tracks=5, audio_tracks=1, fps=s.sequence_fps)
    version = ops.load_state(ep).get("version")
    plan_file = pdir / f"bauplan_v{version}.json"
    od = Path(ep.settings.onedrive_root or ".") / ep.settings.templates_dir / "kuenstler.json"
    artists = store.read_json(od if od.exists() else templates_dir / "kuenstler.json", {})
    llm_cache = pdir / "autoframe.json"

    def frame_box(p: Path):
        from .autoframe import subject_box
        from .llm import Llm
        return subject_box(Llm(ep.settings), p, llm_cache)

    return ToolContext(recipes=recipes, settings={"art_px": s.art_size_px, "landscape_px": s.landscape_px, "mask": s.mask,
                                                  "artwork_effects": list(s.artwork_effects), "fps": s.sequence_fps},
                       masks=templates_dir / "masken", nested_preset=str(nested), credit_mogrt=ops.discover_credit_mogrts(templates_dir / "mogrt"),
                       artist_db={k.lower(): v for k, v in artists.items()}, cache=pdir, frame_box=frame_box,
                       calibration=ops.calibration(), plan=store.read_json(plan_file, None) if version and plan_file.exists() else None,
                       scenes={sc.id: {"titel": sc.titel, "status": sc.status} for sc in ep.scenes()})


def dispatch(ctx: ToolContext, method: str, args: dict) -> Any:
    if method == "tools.config":
        return config(ctx)
    if method == "tools.effects":
        return effects(ctx, [str(i) for i in args["ids"]], [{"dur": float(c["dur"])} for c in args["clips"]])
    if method == "tools.audiofade":
        return audiofade(ctx, float(args["dur"]), args.get("ein"), args.get("aus"))
    if method == "tools.artwork":
        return artwork(ctx, str(args["path"]), float(args["dur"]))
    if method == "tools.credit":
        return credit(ctx, str(args["art"]), args.get("path"), args.get("name"), args.get("text"), float(args["dur"]))
    if method == "tools.scene_at":
        return scene_at(ctx, float(args["time"]))
    raise ValueError(f"Unbekannte Methode: {method}")
