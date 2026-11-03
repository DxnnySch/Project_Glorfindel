"""Übergänge wie im Ursprungsschnitt: Cross Dissolve (0,42 s) an Überlagerungen, Gleichleistungs-Blenden am Serienton."""
import math

import pytest

from glorfindel.premiere_plan import build_plan, equal_power_keyframes, load_recipes
from test_premiere_plan import env, package  # noqa: F401 – Fixtures

DISSOLVE = "AE.ADBE Cross Dissolve New"


def test_recipes_carry_the_measured_transition_rules():
    u = load_recipes()["uebergaenge"]
    assert u["video"]["match_name"] == DISSOLVE and u["video"]["dauer"] == pytest.approx(25 / 60, abs=1e-3)
    assert u["audio"]["dauer"] == 1.0 and u["audio"]["kurve"] == "gleichleistung"


def test_overlays_get_cross_dissolve_at_head_and_tail(env):  # noqa: F811
    plan = build_plan(package(), env)
    assert plan["transitions"]["video"]["match_name"] == DISSOLVE
    for kind in ("artwork", "credit"):
        for c in (c for c in plan["clips"] if c["kind"] == kind):
            d = min(25 / 60, (c["end"] - c["start"]) / 2)
            assert c["uebergang"] == {"ein": pytest.approx(d, abs=1e-3), "aus": pytest.approx(d, abs=1e-3)}, (kind, c["name"])
    for c in (c for c in plan["clips"] if c["kind"] in ("still", "voice", "adjust", "bars")):
        assert "uebergang" not in c                                            # Standbild/Blur/Sprecher bleiben hart geschnitten


def test_episode_clips_dissolve_only_at_scene_edges_and_fade_their_audio(env):  # noqa: F811
    plan = build_plan(package(), env)
    first, second, other = sorted((c for c in plan["clips"] if c["kind"] == "episode"), key=lambda c: c["start"])
    assert first["scene"] == second["scene"] != other["scene"] and abs(first["end"] - second["start"]) < 0.05
    d = pytest.approx(25 / 60, abs=1e-3)
    assert first["uebergang"] == {"ein": d, "aus": 0.0}                         # Szenenanfang: ein, Schnitt in der Szene: hart
    assert second["uebergang"] == {"ein": 0.0, "aus": d}
    assert other["uebergang"] == {"ein": d, "aus": d}
    assert (first["ton_blende"]["ein"], first["ton_blende"]["aus"]) == (1.0, 0.2)   # Szenenkante lang, harter Quellsprung kurz
    assert (second["ton_blende"]["ein"], second["ton_blende"]["aus"]) == (0.2, 1.0)
    assert (other["ton_blende"]["ein"], other["ton_blende"]["aus"]) == (1.0, 1.0)
    for c in (first, second, other):
        b = c["ton_blende"]
        assert b["kurve"] == "gleichleistung" and b["keyframes"][0][0] == 0.0
        assert all(0.0 <= g <= 1.0 for _, g in b["keyframes"]) and [t for t, _ in b["keyframes"]] == sorted(t for t, _ in b["keyframes"])
        assert b["keyframes"][-1][0] <= c["end"] - c["start"] + 1e-9                # nie hinter dem Clipende


def test_equal_power_curve_keeps_loudness_constant():
    kfs = equal_power_keyframes(10.0, ein=1.0, aus=1.0)
    assert kfs[0] == [0.0, 0.0] and kfs[-1] == [10.0, 0.0]
    mid_in = next(g for t, g in kfs if t == pytest.approx(0.5, abs=1e-6))
    assert mid_in == pytest.approx(math.sin(math.pi / 4), abs=1e-3)           # −3 dB in der Mitte der Blende
    full = [g for t, g in kfs if 1.0 <= t <= 9.0]
    assert full and all(g == 1.0 for g in full)
    # Gleichleistung: Einblende² + Ausblende² (gespiegelt) = 1
    for t, g in kfs:
        if t <= 1.0:
            assert g * g + math.cos(math.pi / 2 * t) ** 2 == pytest.approx(1.0, abs=1e-3)


def test_short_clips_shrink_the_fades_instead_of_overlapping():
    kfs = equal_power_keyframes(1.2, ein=1.0, aus=1.0)
    ts = [t for t, _ in kfs]
    assert ts == sorted(ts) and max(ts) == pytest.approx(1.2) and all(0.0 <= g <= 1.0 for _, g in kfs)
    assert equal_power_keyframes(0.0, 1.0, 1.0) == []
    assert equal_power_keyframes(5.0, 0.0, 0.0) == []
