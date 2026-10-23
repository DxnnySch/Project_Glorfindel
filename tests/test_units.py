"""Szenen = Messeinheiten (nicht löschbar, nicht automatisch im Video), Segmente frei und löschbar."""
import io

import pytest
from docx import Document
from fastapi.testclient import TestClient

from glorfindel import store
from glorfindel.api import create_app
from glorfindel.config import Settings, Thresholds
from glorfindel.deps import AppState
from glorfindel.models import CommentBlock, Scene, Segment
from glorfindel.rough_cut import build_package, load_template
from glorfindel.scenes import coverage, in_video, overlap_problems


def seg(a, b, **kw):
    return Segment(**{"in": a, "out": b}, **kw)


def sc(i, bereich=None, segs=(), **kw):
    return Scene(id=f"sz_{i:02d}", titel=kw.pop("titel", f"S{i}"), bereich=bereich, segmente=list(segs), **kw)


# ---- Abdeckung: Segment = Szene, mehrere Szenen oder Teil einer Szene ----
def test_segment_can_be_scene_span_several_or_part():
    scenes = [sc(1, [0, 30], [seg(0, 30)]),                       # ganze Szene 1
              sc(2, [30, 60], [seg(40, 48)]),                     # Teil von Szene 2
              sc(3, [60, 90]), sc(4, [90, 120]),
              sc(5, [120, 150], [seg(70, 100)])]                  # in Szene 5 angelegt, liegt in Szene 3 und 4
    cov = coverage(scenes)
    assert cov["segments"]["sz_01"][0]["nr"] == [1] and cov["segments"]["sz_01"][0]["anteil"]["sz_01"] == 1.0
    assert cov["segments"]["sz_02"][0]["nr"] == [2]
    assert cov["segments"]["sz_02"][0]["anteil"]["sz_02"] == pytest.approx(0.267, abs=0.01)
    assert cov["segments"]["sz_05"][0]["nr"] == [3, 4]
    assert {t["scene"] for t in cov["touched"]["sz_03"]} == {"sz_05"} and cov["touched"]["sz_05"] == []


def test_scene_without_segment_or_comment_is_not_in_video():
    assert not in_video(sc(1, [0, 10]))
    assert in_video(sc(2, [0, 10], [seg(1, 3)])) and in_video(sc(3, [0, 10], kommentar=[CommentBlock(text="x")]))


def test_overlap_problems_across_scenes():
    a, b = sc(1, [0, 30], [seg(10, 25)]), sc(2, [30, 60], [seg(20, 40)])
    pr = overlap_problems([a, b])
    assert "überschneidet" in pr["sz_01"][0] and "überschneidet" in pr["sz_02"][0]
    assert overlap_problems([sc(1, [0, 30], [seg(0, 10), seg(10, 20)])]) == {}


def test_rough_cut_has_only_segments_of_scenes_with_material():
    scenes = [sc(i, [i * 10, i * 10 + 10]) for i in range(1, 6)] + [sc(6, [60, 70], [seg(61, 65)])]
    pkg = build_package([s for s in scenes if in_video(s)], slug="S", template=load_template(), th=Thresholds())
    assert [c["scene"] for c in pkg["tracks"]["V1"] if c["type"] == "scene_segment"] == ["sz_06"]
    assert not [w for w in pkg["warnings"] if "noch kein Serienmaterial" in w]


# ---- API ----
@pytest.fixture
def client(tmp_path):
    root = tmp_path / "OD"
    root.mkdir()
    c = TestClient(create_app(AppState(Settings(onedrive_root=str(root), user="danny"), persist=False)), base_url="http://localhost")
    c.root = root
    c.post("/api/episodes", json={"season": 3, "episode": 1})
    return c


def _ep(client):
    from glorfindel.service import Episode
    return Episode(client.app.state.gl.settings, 3, 1)


def legacy_project(client):
    """Altes Board-Anlegen: je erkannter Szene ein 9,5-s-Segment, kein Bereich."""
    ep = _ep(client)
    proposals = [{"start": 0.0, "end": 30.0}, {"start": 34.38, "end": 60.0}, {"start": 60.0, "end": 90.0}, {"start": 90.0, "end": 120.0}]
    store.write_json(ep.p.cache() / "board.json", {"scenes": proposals})
    a = ep.create_scene(titel="Szene ab 00:00.00", segmente=[seg(0, 9.5)])                    # unbearbeitet -> weg
    b = ep.create_scene(titel="Szene ab 00:34.38", segmente=[seg(34.4, 43.9)])                  # unbearbeitet -> weg
    c = ep.create_scene(titel="Szene ab 01:00.00", segmente=[seg(60, 69.5, notiz="Kontext")])  # mit Notiz -> bleibt
    d = ep.create_scene(titel="Szene ab 01:30.00", segmente=[seg(92, 99)])                      # selbst gesetzt -> bleibt
    d.kommentar = [CommentBlock(text="Mein Kommentar", segment=0)]
    ep.save_scene(d)
    return ep, (a, b, c, d)


def test_legacy_projects_are_migrated_once_with_backup(client):
    ep, (a, b, c, d) = legacy_project(client)
    scenes = {s["id"]: s for s in client.get("/api/ep/3/1/scenes").json()}
    assert scenes[a.id]["bereich"] == [0.0, 30.0] and scenes[a.id]["segmente"] == []
    assert scenes[b.id]["bereich"] == [34.38, 60.0] and scenes[b.id]["segmente"] == []
    assert len(scenes[c.id]["segmente"]) == 1 and scenes[c.id]["segmente"][0]["notiz"] == "Kontext"
    assert scenes[d.id]["segmente"][0]["in"] == 92 and scenes[d.id]["kommentar"][0]["segment"] == 0
    assert [scenes[x.id]["nr"] for x in (a, b, c, d)] == [1, 2, 3, 4]
    assert (ep.p.gl / "sicherung" / f"{a.id}_vor_einheiten.json").exists()
    assert any("Messeinheiten" in entry["was"] for entry in client.get("/api/ep/3/1/log").json())
    assert ep.project().einheiten_migriert
    # Zweiter Aufruf ändert nichts mehr: ein danach neu gesetztes Segment bleibt erhalten
    sc_a = ep.scene(a.id)
    sc_a.segmente = [seg(0, 9.5)]
    ep.save_scene(sc_a)
    client.get("/api/ep/3/1/scenes")
    assert len(ep.scene(a.id).segmente) == 1


def test_migration_waits_when_no_board_data_is_available(client):
    ep = _ep(client)
    s = ep.create_scene(titel="Szene ab 00:10.00", segmente=[seg(10, 19.5)])
    client.get("/api/ep/3/1/scenes")
    assert ep.scene(s.id).bereich is None and len(ep.scene(s.id).segmente) == 1   # nichts geraten
    assert not ep.project().einheiten_migriert


def test_scenes_with_range_cannot_be_deleted_but_segments_can(client):
    ep, (a, b, c, d) = legacy_project(client)
    client.get("/api/ep/3/1/scenes")                                   # Umstellung
    r = client.delete(f"/api/ep/3/1/scenes/{a.id}")
    assert r.status_code == 409 and "Messeinheiten" in r.json()["detail"]
    assert a.id in [x["id"] for x in client.get("/api/ep/3/1/scenes").json()]
    sc_d = [x for x in client.get("/api/ep/3/1/scenes").json() if x["id"] == d.id][0]
    sc_d["segmente"], sc_d["kommentar"] = [], []
    assert client.put(f"/api/ep/3/1/scenes/{d.id}", json=sc_d).status_code == 200      # Segment löschen geht
    assert ep.scene(d.id).segmente == []
    loose = client.post("/api/ep/3/1/scenes", json={"titel": "lose"}).json()["id"]      # ohne Bereich bleibt löschbar
    assert client.delete(f"/api/ep/3/1/scenes/{loose}").status_code == 200


def test_list_reports_coverage_for_spanning_segment(client):
    ep = _ep(client)
    for i, (a, b) in enumerate([(0, 30), (30, 60), (60, 90)]):
        ep.create_scene(titel=f"S{i + 1}", bereich=[a, b])
    first = ep.scenes()[0]
    first.segmente = [seg(20, 70)]                                    # Anfang in Szene 1, reicht über 2 bis in 3
    ep.save_scene(first)
    rows = {r["titel"]: r for r in client.get("/api/ep/3/1/scenes").json()}
    assert rows["S1"]["segmente_info"][0]["nr"] == [1, 2, 3]
    assert [t["nr"] for t in rows["S2"]["beruehrt"]] == [1] and [t["nr"] for t in rows["S3"]["beruehrt"]] == [1]
    assert rows["S1"]["beruehrt"] == []


def test_word_export_only_lists_scenes_with_material(client):
    ep = _ep(client)
    for i in range(1, 6):
        ep.create_scene(titel=f"Leer{i}", bereich=[i * 10, i * 10 + 10])
    ep.create_scene(titel="Mit Segment", bereich=[100, 110], segmente=[seg(101, 105)])
    r = client.get("/api/ep/3/1/script.docx")
    heads = [p.text for p in Document(io.BytesIO(r.content)).paragraphs if p.style.name == "Heading 1"]
    assert len(heads) == 1 and "Mit Segment" in heads[0]


def test_migration_keeps_auto_segment_that_carries_an_implicit_comment(client):
    """Alte Kommentare haben keine Segmentangabe und hängen am letzten Segment: dieses Segment darf nicht verschwinden."""
    ep = _ep(client)
    store.write_json(ep.p.cache() / "board.json", {"scenes": [{"start": 0.0, "end": 30.0}, {"start": 30.0, "end": 60.0}]})
    a = ep.create_scene(titel="Szene ab 00:00.00", segmente=[seg(0, 9.5)])
    a.kommentar = [CommentBlock(text="Alter Kommentar ohne Segmentbezug")]       # segment=None
    ep.save_scene(a)
    b = ep.create_scene(titel="Szene ab 00:30.00", segmente=[seg(30, 39.5)])
    rows = {r["id"]: r for r in client.get("/api/ep/3/1/scenes").json()}
    assert len(rows[a.id]["segmente"]) == 1 and rows[a.id]["kommentar"][0]["text"].startswith("Alter")
    assert rows[b.id]["segmente"] == [] and rows[b.id]["bereich"] == [30.0, 60.0]
