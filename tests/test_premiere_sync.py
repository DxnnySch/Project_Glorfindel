"""Abgleich Premiere → App: gekürzte, verlängerte und geteilte Serienclips werden zu Segmenten; veraltete Standbilder werden erkannt und getauscht."""
from pathlib import Path

import pytest

from glorfindel import premiere_ops, premiere_sync
from glorfindel.models import CommentBlock, Scene, Segment

from test_premiere_ops import FakeHub, ep, seg  # noqa: F401 – Fixtures
from conftest import needs_ffmpeg

pytestmark = needs_ffmpeg
VORLAGEN = Path(__file__).resolve().parents[1] / "vorlagen"


def _dump(*items):
    """Sequenz-Auszug wie vom Panel: items = (Name, Start, Ende, In, Out)."""
    rows = [{"name": n, "start": a, "end": b, "in": i, "out": o} for n, a, b, i, o in items]
    return {"name": "Rohschnitt", "tracks": [{"track": "V4", "count": len(rows), "items": rows}, {"track": "A4", "count": 1, "items": [{"name": "x", "start": 0, "end": 1, "in": 0, "out": 1}]}]}


class SyncHub(FakeHub):
    def __init__(self, dump=None):
        super().__init__()
        self.dump = dump

    def call(self, op, args=None, timeout=60, on_event=None):
        if op == "sequence.dump":
            self.calls.append((op, args))
            return self.dump
        return super().call(op, args, timeout, on_event)


def _scene():
    s = Scene(id="sz_01", titel="T", segmente=[Segment(**{"in": 2, "out": 8, "notiz": "n"}), Segment(**{"in": 12, "out": 17})],
              kommentar=[CommentBlock(text="x", segment=1)])
    return s


def test_unchanged_clips_give_no_changes():
    d = _dump(("sz_01 Segment 1", 0, 6, 2, 8), ("sz_01 Segment 2", 6, 11, 12, 17))
    assert premiere_sync.compare([_scene()], premiere_sync.pieces_from_dump(d)) == []


def test_extended_and_shortened_clips_become_new_in_out_points():
    d = _dump(("sz_01 Segment 1", 0, 5, 2, 7), ("sz_01 Segment 2", 5, 13, 12, 20))
    ch = premiere_sync.compare([_scene()], premiere_sync.pieces_from_dump(d))
    assert [(c["typ"], c["index"]) for c in ch] == [("geaendert", 0), ("geaendert", 1)]
    assert ch[0]["neu"] == [pytest.approx([2.0, 7.0], abs=0.05)] and ch[1]["neu"] == [pytest.approx([12.0, 20.0], abs=0.05)]   # auf Bildraster eingerastet
    sc = _scene()
    premiere_sync.apply([sc], ch)
    assert [(s.in_, s.out) for s in sc.segmente] == [pytest.approx((2.0, 7.0), abs=0.05), pytest.approx((12.0, 20.0), abs=0.05)]


def test_cut_in_the_middle_splits_the_segment_and_keeps_comments_on_the_last_part():
    d = _dump(("sz_01 Segment 1", 0, 3, 2, 5), ("sz_01 Segment 1", 3, 5, 6, 8), ("sz_01 Segment 2", 5, 10, 12, 17))
    sc = _scene()
    ch = premiere_sync.compare([sc], premiere_sync.pieces_from_dump(d))
    assert [c["typ"] for c in ch] == ["geteilt"] and ch[0]["neu"] == [pytest.approx([2.0, 5.0], abs=0.05), pytest.approx([6.0, 8.0], abs=0.05)]
    premiere_sync.apply([sc], ch)
    assert [s.notiz for s in sc.segmente] == ["n", "", ""] and len(sc.segmente) == 3 and sc.segmente[2].in_ == 12.0
    assert sc.kommentar[0].segment == 2                               # Kommentar bleibt am letzten Segment


def test_contiguous_pieces_after_a_razor_cut_stay_one_segment():
    d = _dump(("sz_01 Segment 1", 0, 3, 2, 5), ("sz_01 Segment 1", 3, 6, 5, 8), ("sz_01 Segment 2", 6, 11, 12, 17))
    assert premiere_sync.compare([_scene()], premiere_sync.pieces_from_dump(d)) == []


def test_deleted_clip_is_only_reported_and_offset_is_removed():
    d = _dump(("sz_01 Segment 1", 0, 6, 12.0, 18.0))                   # Premiere-Zeit = Episodenzeit + 10
    ch = premiere_sync.compare([_scene()], premiere_sync.pieces_from_dump(d, off=10.0))
    assert [(c["typ"], c["index"]) for c in ch] == [("entfernt", 1)]
    sc = _scene()
    assert premiere_sync.apply([sc], ch) == [] and len(sc.segmente) == 2


def test_stale_stills_and_structure():
    r = premiere_sync.stale_stills({"1.png": 20.0, "2.png": 30.0}, {"1.png": 17.0, "2.png": 30.0})
    assert r == {"tausch": {"1.png": 20.0}, "struktur": False}
    assert premiere_sync.stale_stills({"1.png": 1.0, "2.png": 2.0}, {"1.png": 1.0})["struktur"] is True


def test_full_flow_read_apply_and_swap_stills(ep):  # noqa: F811
    premiere_ops.build_in_premiere(ep, VORLAGEN, hub=FakeHub())
    assert premiere_ops.sync_state(ep) == {"gebaut": True, "tausch": [], "struktur": False}
    sid = ep.scenes()[0].id
    dump = _dump((f"{sid} Segment 1", 0, 6, 2, 8), (f"{sid} Segment 2", 6, 14, 12, 20))   # zweiter Serienclip um 3 s verlängert
    hub = SyncHub(dump)
    r = premiere_ops.read_from_premiere(ep, apply=False, hub=hub)
    assert [(c["typ"], c["index"]) for c in r["changes"]] == [("geaendert", 1)] and r["angewendet"] is False
    assert ep.scenes()[0].segmente[1].out == 17 and r["sync"]["tausch"] == []        # nur gelesen, nichts verändert
    r = premiere_ops.read_from_premiere(ep, apply=True, hub=hub)
    assert ep.scenes()[0].segmente[1].out == pytest.approx(20.0, abs=0.05) and r["sync"]["tausch"] == ["1.png"]   # Anzeige: Tausch nötig
    hub2 = SyncHub()
    out = premiere_ops.refresh_stills(ep, hub=hub2)
    st = premiere_ops.load_state(ep)
    sdir = Path(st["stills_dir"])
    assert out["getauscht"] == 1 and (sdir / "1_r1.png").exists() and (sdir / "1.png").exists()
    assert hub2.calls[0][1]["swaps"] == [{"from": str(sdir / "1.png"), "to": str(sdir / "1_r1.png")}]
    assert st["stills"]["1.png"] == pytest.approx(20.0, abs=0.05) and premiere_ops.sync_state(ep)["tausch"] == []
    assert premiere_ops.refresh_stills(ep, hub=hub2)["getauscht"] == 0
