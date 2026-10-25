"""Realistischer Premiere-Plan mit stabilen Pfaden – Vertrag zwischen Python-Builder und Panel (JS-Tests nutzen dieselbe Datei)."""
import json
import tempfile
from pathlib import Path

from PIL import Image

from glorfindel.config import Thresholds
from glorfindel.models import AssetRef, CommentBlock, Scene, Segment
from glorfindel.premiere_plan import PlanEnv, build_plan, load_recipes, with_library
from glorfindel.rough_cut import build_package, load_template

FIXTURE = Path(__file__).resolve().parents[1] / "premiere-panel" / "test" / "fixtures" / "plan.json"
STABLE_ROOT = "F:/OneDrive"


def make_plan() -> dict:
    tpl, th = load_template(), Thresholds()
    seg = lambda a, b: Segment(**{"in": a, "out": b})  # noqa: E731
    scenes = [
        Scene(id="sz_01", titel="Schmiede", segmente=[seg(100, 106), seg(120, 125)],
              kommentar=[CommentBlock(sprecher="philipp", text=" ".join(["wort"] * 40),
                                      anker=[AssetRef(asset="a1", von=2, bis=14), AssetRef(asset="a2", von=8, bis=26)])]),
        Scene(id="sz_02", titel="Hafen", segmente=[seg(300, 304)],
              kommentar=[CommentBlock(sprecher="danny", text="kurz und knapp hier", anker=[AssetRef(asset="a1", von=0, bis=3, layout="doppel_links"),
                                                                                         AssetRef(asset="a2", von=0, bis=3, layout="doppel_rechts")])]),
    ]
    assets = {"a1": {"path": "Bilder/alan lee - hafen.jpg", "credit": "alan lee", "contour_color": "#d45329"},
              "a2": {"path": "Bilder/john howe.jpg"}}
    al = {"scenes": {"sz_01": [{"block": 0, "rec": "r1", "in": 10.0, "out": 22.0, "words": []}]}}
    pkg = build_package(scenes, slug="S3 E1", template=tpl, th=th, assets=assets, alignment=al)
    for tr in pkg["tracks"].values():
        for c in tr:
            if c["type"] == "comment" and not c.get("placeholder"):
                c["rec_path"] = "Aufnahmen/philipp.wav"
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "OD"
        (root / "Bilder").mkdir(parents=True)
        Image.new("RGB", (2000, 1000)).save(root / "Bilder" / "alan lee - hafen.jpg")
        Image.new("RGB", (800, 1200)).save(root / "Bilder" / "john howe.jpg")
        env = PlanEnv(root=root, episode_media=root / "cache" / "S3_E1_ref_cfr.mp4", stills_dir=root / "Videoelemente",
                      credit=lambda text, art, x: root / "credits" / f"{art}_{abs(hash((text, x))) % 10**6}.png",
                      image_size=lambda p: Image.open(p).size, recipes=with_library(load_recipes(), json.loads((Path(__file__).resolve().parents[1] / "vorlagen" / "effekt_bibliothek.json").read_text(encoding="utf-8"))),
                      premiere={"aep": f"{STABLE_ROOT}/Videomaterial/Programm-Vorgaben/AfterFX/Play-Pause.aep", "comp": "Play-Pause",
                                "pause_in": 28.7, "play_in": 0.0, "preset": "C:/cache/rohschnitt.sqpreset", "video_tracks": 14, "audio_tracks": 16,
                                "pause_media": f"{STABLE_ROOT}/Videomaterial/VFX/Pause.mov", "play_media": "C:/cache/anim/Play.mov",
                                "mask_dir": "C:/vorlagen/masken", "mask_mode": "auto", "landscape_px": 1536, "nested_preset": "C:/cache/artwork.sqpreset", "art_px": 1000,
                                "bars_png": "C:/cache/anim/Schwarzstreifen.png"},
                      doppel=tpl["doppelbild"])
        plan = build_plan(pkg, env)
        txt = json.dumps(plan, ensure_ascii=False).replace(str(root).replace("\\", "\\\\"), STABLE_ROOT)
    plan = json.loads(txt)
    for m in plan["media"]:
        m["path"] = m["path"].replace("\\", "/")
    # Credit-Dateinamen stabil machen (hash() ist je Prozess verschieden)
    for m in plan["media"]:
        if m["kind"] == "credit":
            m["path"] = f"{STABLE_ROOT}/credits/credit_{m['id']}.png"
    return plan
