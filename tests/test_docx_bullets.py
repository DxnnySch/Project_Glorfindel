from glorfindel.models import AssetRef, CommentBlock, Scene, Segment
from glorfindel.script_docx import apply_import, export_docx, import_docx


def test_bullets_roundtrip_with_anchors(tmp_path):
    sc = [Scene(id="sz_01", titel="Schmiede", segmente=[Segment(**{"in": 1, "out": 2})], kommentar=[
        CommentBlock(sprecher="danny", modus="stichpunkte", stichpunkte=["Celebrimbor Schmiede", "Annatar Ringe", "Fazit"],
                     anker=[AssetRef(asset="a1", von=0, bis=2, einheit="stichpunkt"),
                            AssetRef(karte="k1", von=1, bis=None, einheit="stichpunkt")]),
        CommentBlock(sprecher="philipp", text="Ein normaler Block danach"),
    ])]
    p = tmp_path / "b.docx"
    export_docx(sc, p)
    res = import_docx(p)
    k = res.scenes["sz_01"]["kommentar"]
    assert k[0].modus == "stichpunkte" and k[0].stichpunkte == ["Celebrimbor Schmiede", "Annatar Ringe", "Fazit"]
    assert [(a.asset, a.karte, a.von, a.bis, a.einheit) for a in k[0].anker] == \
        [("a1", None, 0, 2, "stichpunkt"), (None, "k1", 1, None, "stichpunkt")]
    assert k[1].modus == "text" and k[1].text == "Ein normaler Block danach"
    assert apply_import(sc, res) == []


def test_bullet_edit_in_word_is_imported(tmp_path):
    from docx import Document
    sc = [Scene(id="sz_01", kommentar=[CommentBlock(sprecher="danny", modus="stichpunkte", stichpunkte=["alt"])])]
    p = tmp_path / "e.docx"
    export_docx(sc, p)
    d = Document(str(p))
    d.add_paragraph("neuer Punkt", style="List Bullet")
    d.save(str(p))
    res = import_docx(p)
    assert apply_import(sc, res) == ["sz_01"] and sc[0].kommentar[0].stichpunkte == ["alt", "neuer Punkt"]
