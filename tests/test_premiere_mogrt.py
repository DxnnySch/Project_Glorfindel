"""Credits als editierbarer Text: Motion-Graphics-Vorlage aus vorlagen/mogrt, Rückfall auf PNG."""
import json

import pytest

from glorfindel.premiere_ops import discover_credit_mogrts
from glorfindel.premiere_plan import build_plan
from test_premiere_plan import env, package  # noqa: F401 – Fixtures


def test_discovery_finds_templates_by_credit_type(tmp_path):
    d = tmp_path / "mogrt"
    d.mkdir()
    for n in ("Credit Amazon.mogrt", "Credit Artwork.mogrt", "Credit Musik.mogrt", "Egal.mogrt", "Credit Artwork.txt"):
        (d / n).write_bytes(b"x")
    found = discover_credit_mogrts(d)
    assert set(found) == {"amazon", "artwork", "musik"}
    assert found["artwork"].endswith("Credit Artwork.mogrt")
    assert discover_credit_mogrts(tmp_path / "gibtsnicht") == {}


def test_credits_use_the_text_template_where_one_exists_and_keep_the_png_as_fallback(env):  # noqa: F811
    env.premiere["credit_mogrt"] = {"artwork": "C:/vorlagen/mogrt/Credit Artwork.mogrt"}
    plan = build_plan(package(), env)
    credits = [c for c in plan["clips"] if c["kind"] == "credit"]
    art = [c for c in credits if c["art"] == "artwork"]
    ama = [c for c in credits if c["art"] == "amazon"]
    assert art and ama
    for c in art:
        assert c["text_modus"] == "mogrt" and c["mogrt"]["path"].endswith("Credit Artwork.mogrt")
        assert c["mogrt"]["text"] == c["name"] and c["media"]                    # PNG bleibt als Rückfall registriert
    assert all("mogrt" not in c and c.get("text_modus", "png") == "png" for c in ama)
    json.dumps(plan)


def test_double_image_credits_move_sideways_by_the_layout_offset(env):  # noqa: F811
    from glorfindel.models import AssetRef, CommentBlock, Scene
    from test_premiere_plan import TH, TPL, seg
    from glorfindel.rough_cut import build_package
    scenes = [Scene(id="sz_01", titel="Doppel", segmente=[seg(100, 108)],
                    kommentar=[CommentBlock(sprecher="philipp", text="wort " * 20,
                                            anker=[AssetRef(asset="a1", von=0, bis=10, layout="doppel_links"), AssetRef(asset="a2", von=0, bis=10, layout="doppel_rechts")])])]
    assets = {"a1": {"path": "Bilder/alan lee - hafen.jpg", "credit": "alan lee"}, "a2": {"path": "Bilder/john howe.jpg"}}
    env.premiere["credit_mogrt"] = {"artwork": "C:/v/Credit Artwork.mogrt"}
    plan = build_plan(build_package(scenes, slug="S3 E1", template=TPL, th=TH, assets=assets), env)
    dx = sorted(c["mogrt"]["dx"] for c in plan["clips"] if c["kind"] == "credit" and c.get("mogrt"))
    assert dx == [pytest.approx(0.27 - 0.5), pytest.approx(0.73 - 0.5)]
    single = build_plan(package(), env)
    assert {c["mogrt"]["dx"] for c in single["clips"] if c["kind"] == "credit" and c.get("mogrt")} == {0.0}
