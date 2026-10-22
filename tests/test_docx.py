from docx import Document

from glorfindel.models import AssetRef, CommentBlock, Scene, Segment
from glorfindel.script_docx import apply_import, export_docx, import_docx


def make_scenes():
    return [
        Scene(id="sz_01", strang="eregion", titel="Schmiede", segmente=[Segment(**{"in": 10, "out": 15})],
              kommentar=[
                  CommentBlock(sprecher="philipp", text="Hier sehen wir Celebrimbor bei der Arbeit",
                               anker=[AssetRef(asset="art_1", von=2, bis=5)]),
                  CommentBlock(sprecher="danny", text="Und das passt gut",
                               anker=[AssetRef(karte="k_moria", von=0, bis=None)]),
              ]),
        Scene(id="sz_02", strang="numenor", titel="Hafen", segmente=[Segment(**{"in": 40, "out": 44})],
              kommentar=[CommentBlock(sprecher="danny", text="Zweiter Teil")]),
    ]


def test_roundtrip_preserves_text_and_anchors(tmp_path):
    p = tmp_path / "s.docx"
    sc = make_scenes()
    export_docx(sc, p, title="S3 E1")
    res = import_docx(p)
    assert res.order == ["sz_01", "sz_02"]
    k = res.scenes["sz_01"]["kommentar"]
    assert [c.sprecher for c in k] == ["philipp", "danny"]
    assert k[0].text == "Hier sehen wir Celebrimbor bei der Arbeit"
    assert (k[0].anker[0].asset, k[0].anker[0].von, k[0].anker[0].bis) == ("art_1", 2, 5)
    assert (k[1].anker[0].karte, k[1].anker[0].von, k[1].anker[0].bis) == ("k_moria", 0, None)
    assert apply_import(sc, res) == []  # unverändert -> nichts geändert


def test_edit_in_word_and_free_blocks(tmp_path):
    p = tmp_path / "s.docx"
    sc = make_scenes()
    export_docx(sc, p)
    d = Document(str(p))
    for para in d.paragraphs:
        for r in para.runs:
            if "Zweiter" in r.text:
                r.text = r.text.replace("Zweiter", "Dritter")
    # freien Block ergänzen (Werbung)
    d.add_heading("Werbung", level=1)
    d.add_paragraph("Hier kommt der Werbetext.")
    d.save(str(p))
    res = import_docx(p)
    assert apply_import(sc, res) == ["sz_02"]
    assert sc[1].kommentar[0].text == "Dritter Teil"
    assert res.free_blocks[0]["titel"] == "Werbung" and res.free_blocks[0]["after"] == "sz_02"


def test_speaker_filter_and_hidden_markers(tmp_path):
    p = tmp_path / "d.docx"
    export_docx(make_scenes(), p, speaker="danny", show_markers=False)
    res = import_docx(p)
    assert [c.sprecher for c in res.scenes["sz_01"]["kommentar"]] == ["danny"]
    assert res.scenes["sz_01"]["kommentar"][0].anker == []


def test_free_blocks_exported(tmp_path):
    p = tmp_path / "f.docx"
    export_docx(make_scenes(), p, free_blocks=[{"after": None, "titel": "Intro", "text": "Willkommen"}])
    res = import_docx(p)
    assert res.free_blocks == [{"after": None, "titel": "Intro", "text": "Willkommen"}]
