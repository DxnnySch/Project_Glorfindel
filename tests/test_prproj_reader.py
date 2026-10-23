"""Projektleser gegen das echte Ursprungsprojekt (S2 E7); ohne die Datei übersprungen."""
from pathlib import Path

import pytest

from glorfindel.prproj_reader import Project, effect_recipe

REAL = Path(r"F:\OneDrive\Mythen-Archiv\Videos\S2 E7\Mythen - S2 E7_1.prproj")
pytestmark = pytest.mark.skipif(not REAL.exists(), reason="echtes Projekt nicht verfügbar")


@pytest.fixture(scope="module")
def proj():
    return Project.open(REAL)


def test_sequences_and_main_structure(proj):
    seqs = proj.sequences()
    names = [s.name for s in seqs]
    assert len(seqs) == 41 and "MythenAusMittelerdeVideo" in names and {"Play", "Pause", "S2 E7 Sequenz"} <= set(names)
    main = proj.sequence("MythenAusMittelerdeVideo")
    assert len(main.video) == 14 and len(main.audio) >= 16
    counts = {i + 1: len(v) for i, v in main.video.items()}
    assert counts[1] > 200 and counts[3] > 60 and counts[10] > 80 and counts[9] > 60


def test_artwork_clip_has_the_fancy_effect_chain(proj):
    main = proj.sequence("MythenAusMittelerdeVideo")
    art = next(i for i in main.video[2] if i.name.startswith("Verschachtelte") and len(i.comps) >= 4)
    assert [c.match_name for c in art.comps] == ["AE.ADBE Drop Shadow", "AE.ADBE Geometry", "AE.ADBE Roughen Edges", "AE.ADBE Roughen Edges"]
    fancy_in = art.comps[2]
    rahmen = next(p for p in fancy_in.params if p.name == "Rahmen")
    assert rahmen.time_varying and len(rahmen.keyframes) == 2
    (t0, v0), (t1, v1) = rahmen.keyframes
    assert t0 == pytest.approx(0, abs=0.05) and float(v0) == pytest.approx(500) and t1 == pytest.approx(0.5, abs=0.05) and float(v1) == pytest.approx(8)
    rec = effect_recipe(art.comps[3], art.end - art.start, "end")       # Fancy Out: Zeiten relativ zum Ende
    r2 = next(p for p in rec["params"] if p["name"] == "Rahmen")
    assert r2["keyframes"][-1][0] == pytest.approx(0, abs=0.05) and r2["keyframes"][0][0] < 0


def test_kinds_and_tracks(proj):
    main = proj.sequence("MythenAusMittelerdeVideo")
    kinds = {i.kind for v in main.video.values() for i in v}
    assert {"sequenz", "grafik", "einstellungsebene", "medium"} <= kinds
    pauses = [i for i in main.video[6] if i.name in ("Pause", "Play")]           # V7: Pause/Play
    assert pauses and all(abs((p.end - p.start) - 1.32) < 0.05 for p in pauses)
    blur = [i for i in main.video[1] if i.kind == "einstellungsebene"]
    assert blur and blur[0].comps[0].match_name == "AE.ADBE Gaussian Blur 2"
    credits = [i for i in main.video[9] if i.kind == "grafik"]
    assert credits and credits[0].comps[0].match_name == "AE.ADBE Motion"
