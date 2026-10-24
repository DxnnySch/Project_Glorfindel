"""Abläufe mit Premiere (Bau, Tausch) gegen ein simuliertes Premiere."""
import json
import subprocess
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from glorfindel import premiere_ops
from glorfindel.bridge import BridgeError
from glorfindel.models import Anchor, AssetRef, CommentBlock, Segment
from glorfindel.service import Episode

from conftest import needs_ffmpeg

pytestmark = needs_ffmpeg


class FakeHub:
    connected = True

    def __init__(self, fail=None):
        self.calls, self.fail = [], fail

    def call(self, op, args=None, timeout=60, on_event=None):
        self.calls.append((op, args))
        if on_event:
            on_event("progress", {"done": 1, "of": 2, "text": "halb"})
        if self.fail:
            raise BridgeError(self.fail)
        if op == "plan.run":
            return {"errors": [], "warnings": ["Test-Warnung"], "placed": {"episode": len(args["plan"]["clips"])}}
        if op == "media.swap":
            return {"getauscht": args["swaps"], "fehler": [], "neu_geladen": len(args["refresh"])}
        return {}


def seg(a, b):
    return Segment(**{"in": a, "out": b})


def make_video(path, color, seconds=30, fps=30, size="640x360"):
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c={color}:s={size}:r={fps}:d={seconds}",
                    "-f", "lavfi", "-i", f"sine=frequency=300:duration={seconds}", "-vf", "drawbox=x=0:y=0:w=640:h=40:color=black:t=fill,drawbox=x=0:y=320:w=640:h=40:color=black:t=fill" if size == "640x360" else "null",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path)], check=True)
    return path


@pytest.fixture
def ep(episode_root, tmp_path, monkeypatch):
    # Adobe-Vorgabe ersetzen (Premiere muss für den Test nicht installiert sein)
    monkeypatch.setattr(premiere_ops, "make_sequence_preset", lambda dst, **kw: (dst.write_text("preset", encoding="utf-8"), dst)[1])
    e = Episode.create(episode_root, 3, 1, "Test")
    e.import_source(make_video(e.p.root / "Filme" / "screen.mp4", "red"))
    srcs = e.sources()
    srcs[0].crop = [0, 40, 640, 280]
    e._save_sources(srcs)
    (e.p.root / "Bilder").mkdir()
    Image.new("RGB", (800, 400), (30, 90, 200)).save(e.p.root / "Bilder" / "alan lee - hafen.jpg")
    pipeline = __import__("glorfindel.pipeline", fromlist=["x"])
    pipeline.save_asset(e, {"id": "art_0001", "path": "Bilder/alan lee - hafen.jpg", "credit": "alan lee", "contour_color": "#d45329"})
    s1 = e.create_scene(titel="Schmiede", segmente=[seg(2, 8), seg(12, 17)])
    s1.kommentar = [CommentBlock(sprecher="philipp", text=" ".join(["wort"] * 30), segment=1, anker=[AssetRef(asset="art_0001", von=2, bis=12)])]
    e.save_scene(s1)
    return e


def test_build_creates_reference_stills_plan_and_calls_premiere(ep):
    hub = FakeHub()
    prog = []
    res = premiere_ops.build_in_premiere(ep, ep.settings and Path(__file__).resolve().parents[1] / "vorlagen", progress=lambda p, *a: prog.append(p), hub=hub)
    ref = Path(premiere_ops.load_state(ep)["ref_cfr"])
    assert ref.exists() and ref.name.endswith("_Referenz_CFR.mp4")
    from glorfindel import media
    info = media.probe(ref)
    assert (info["width"], info["height"]) == (1920, 800) and info["fps"] == pytest.approx(23.976, abs=0.01)   # CFR, zugeschnitten
    sdir = ep.p.stills / "Bridge_v1"                                              # eigener Ordner je Bau
    stills = sorted(p.name for p in sdir.glob("*.png"))
    assert stills == ["1.png"] and Image.open(sdir / "1.png").size == (1920, 800)
    op, args = hub.calls[0]
    plan = args["plan"]
    assert op == "plan.run" and plan["calibration"] == {"colorMode": "unit", "keyframeBase": "clip"}
    m = {x["id"]: x for x in plan["media"]}
    assert Path(m[next(c for c in plan["clips"] if c["kind"] == "episode")["media"]]["path"]) == ref
    assert {Path(x["path"]).name for x in plan["media"] if x["kind"] == "still"} == {"1.png"}
    assert Path(plan["preset"]["path"]).exists() and plan["anim_source"]["comp"] == "Play-Pause"
    cred = [x for x in plan["media"] if x["kind"] == "credit"]
    assert cred and all(Path(x["path"]).exists() for x in cred)                  # Credit-PNGs wirklich erzeugt
    st = premiere_ops.load_state(ep)
    assert list(st["stills"]) == ["1.png"] and st["stills"]["1.png"] == pytest.approx(17.0, abs=0.03)   # nur nach dem Segment mit Kommentar and st["active"] == "proxy" and st["sequence"].startswith("Rohschnitt S3 E1")
    assert res["report"]["warnings"] == ["Test-Warnung"] and (premiere_ops.pdir(ep) / f"bericht_v{res['version']}.json").exists()
    assert prog                                                                   # Fortschritt gemeldet


def test_build_without_connection_fails_clearly(ep):
    hub = FakeHub()
    hub.connected = False
    with pytest.raises(BridgeError, match="nicht verbunden"):
        premiere_ops.build_in_premiere(ep, Path(__file__).resolve().parents[1] / "vorlagen", hub=hub)


def _gray(p):                       # RGB statt Grauwert: Rot und Grün haben fast gleiche Helligkeit
    return np.asarray(Image.open(p).convert("RGB"), dtype=float)


def test_swap_uses_parallel_folder_and_never_overwrites(ep):
    root = Path(__file__).resolve().parents[1] / "vorlagen"
    premiere_ops.build_in_premiere(ep, root, hub=FakeHub())
    sdir = Path(premiere_ops.load_state(ep)["stills_dir"])
    proxy_still = _gray(sdir / "1.png").copy()
    proxy_bytes = (sdir / "1.png").read_bytes()
    hq = make_video(premiere_ops.pdir(ep) / "HQ_conform.mp4", "green", seconds=30, fps=24, size="1920x800")
    premiere_ops.remember_hq(ep, str(hq))
    hub2 = FakeHub()
    premiere_ops.swap(ep, "hq", hub=hub2)
    op, args = hub2.calls[0]
    st = premiere_ops.load_state(ep)
    hq_dir = sdir.with_name(sdir.name + "_HQ")
    assert op == "media.swap" and args["refresh"] == []
    assert args["swaps"] == [{"from": st["ref_cfr"], "to": str(hq)}, {"from": str(sdir / "1.png"), "to": str(hq_dir / "1.png")}]
    assert (sdir / "1.png").read_bytes() == proxy_bytes                              # Proxy-Standbild unberührt (Premiere könnte es sperren)
    assert abs(_gray(hq_dir / "1.png") - proxy_still).mean() > 20 and Image.open(hq_dir / "1.png").size == (1920, 800)
    assert st["active"] == "hq"
    with pytest.raises(ValueError, match="bereits"):
        premiere_ops.swap(ep, "hq", hub=hub2)
    hub3 = FakeHub()
    premiere_ops.swap(ep, "proxy", hub=hub3)
    assert hub3.calls[0][1]["swaps"] == [{"from": str(hq), "to": st["ref_cfr"]}, {"from": str(hq_dir / "1.png"), "to": str(sdir / "1.png")}]
    assert (sdir / "1.png").read_bytes() == proxy_bytes and premiere_ops.load_state(ep)["active"] == "proxy"


def test_second_build_does_not_touch_stills_locked_by_premiere(ep, monkeypatch):
    """Premiere hält Standbilder früherer Importe offen: ein neuer Bau darf sie nie überschreiben wollen."""
    root = Path(__file__).resolve().parents[1] / "vorlagen"
    premiere_ops.build_in_premiere(ep, root, hub=FakeHub())
    first = ep.p.stills / "Bridge_v1" / "1.png"
    locked = first.read_bytes()
    import os
    real = os.replace
    monkeypatch.setattr(os, "replace", lambda a, b: (_ for _ in ()).throw(PermissionError("gesperrt")) if Path(b) == first else real(a, b))
    premiere_ops.build_in_premiere(ep, root, hub=FakeHub())
    assert (ep.p.stills / "Bridge_v2" / "1.png").exists() and first.read_bytes() == locked


def test_swap_errors_are_clear(ep):
    with pytest.raises(ValueError, match="noch keinen"):
        premiere_ops.swap(ep, "hq", hub=FakeHub())
    premiere_ops.build_in_premiere(ep, Path(__file__).resolve().parents[1] / "vorlagen", hub=FakeHub())
    with pytest.raises(ValueError, match="HQ-Datei fehlt"):
        premiere_ops.swap(ep, "hq", hub=FakeHub())
    hq = make_video(premiere_ops.pdir(ep) / "HQ.mp4", "green", seconds=30, fps=24, size="1920x800")
    premiere_ops.remember_hq(ep, str(hq))
    with pytest.raises(BridgeError, match="Tausch"):
        h = FakeHub()
        h.call = lambda op, args=None, timeout=60, on_event=None: {"fehler": [{"von": "x", "fehler": "abgelehnt"}], "getauscht": []}
        premiere_ops.swap(ep, "hq", hub=h)
    assert premiere_ops.load_state(ep)["active"] == "proxy"                         # Zustand nur bei Erfolg geändert
