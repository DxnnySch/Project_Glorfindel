"""Credit-Vorlagen mit festem Text: der Text wird in die .mogrt geschrieben, weil Premiere ihn per Skript nicht setzen lässt."""
import base64
import gzip
import io
import json
import re
import struct
import zipfile
from pathlib import Path

import pytest

from glorfindel import mogrt_text

# Textblock (Quelltext-Parameter) aus „Credit Amazon v2.mogrt“: 12 Byte Kopf + FlatBuffer, Text „© amazon studios“
BLOB_B64 = (
    "lAEAAAAAAABEMyIRFAAAAAAADgAKAAQACQAAAAAACAAOAAAAZAAAAAEBXgA4ABAADAAAAAAAAAAAAAAAAAAAAAAANAAzACwAKAAkACAAHAAYAAAAFAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAACAAAAAAAAAAHAF4AAAAAAAABMAAAAGAAAAB8AAAAAADIQjgAAAAAAOBBZma2QAAAAAAAADRDAABcQgAAAAEwAAAAKP///wQABgAEAAAAAAAKAAoA"
    "BwAIAAkACgAAAAAAAAAAAAoACAAFAAYABwAKAAAAAAAAAAEAAAAEAAAAEgAAAEdyYW5kQ2VudHJhbC1MaWdodAAAAQAAAAwAAAAIAAwABAAIAAgAAAAIAAAAUAAAABEAAADCqSBhbWF6"
    "b24gc3R1ZGlvcwAAADQAEAAAAAwAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAIAAAABAA0AAAADAAAAAwAAAAAAKBB9P////j////8////BAAEAAQAAAA="
)
OLD = "© amazon studios"


def read_text(blob: bytes) -> str:
    """Text aus dem Block lesen: das einzige Feld, das auf einen NUL-terminierten UTF-8-String zeigt, dessen Länge davor steht."""
    body = blob[12:]
    for q in range(0, len(body) - 3, 4):
        tgt = q + struct.unpack_from("<I", body, q)[0]
        if tgt <= q or tgt + 4 > len(body):
            continue
        n = struct.unpack_from("<I", body, tgt)[0]
        if 0 < n < 200 and tgt + 4 + n < len(body) and body[tgt + 4 + n] == 0:
            try:
                s = body[tgt + 4:tgt + 4 + n].decode("utf-8")
            except UnicodeDecodeError:
                continue
            if s.isprintable() and "Central" not in s:
                return s
    raise AssertionError("kein Text gefunden")


def test_blob_text_is_replaced_and_the_rest_stays_valid():
    blob = base64.b64decode(BLOB_B64)
    assert read_text(blob) == OLD
    for new in ("© Alan Lee", "© Künstler Ä Ö Ü ß – sehr langer Name, der länger ist als der ursprüngliche Text", "x", "© 日本語"):
        out = mogrt_text.patch_text_blob(blob, OLD, new)
        assert read_text(out) == new
        assert struct.unpack_from("<I", out, 0)[0] == len(out) - 12                 # Kopf: Länge des FlatBuffers
        assert (len(out) - 12) % 4 == 0
        assert out[:12][4:] == blob[:12][4:]                                        # Rest des Kopfes unverändert
        assert out[12:12 + 300].startswith(blob[12:12 + 20])                         # alter Inhalt bleibt (nur ein Verweis wird umgebogen)


def test_blob_rejects_unknown_text():
    with pytest.raises(ValueError):
        mogrt_text.patch_text_blob(base64.b64decode(BLOB_B64), "ganz anderer Text", "x")


def make_template(path: Path) -> Path:
    """Nachbau einer Premiere-Vorlage: definition.json, project.prgraphic (ZIP mit gzip-komprimiertem Projekt), Vorschaubilder."""
    definition = {"capsuleID": "ed2dd5ae-cb29-45ff-9380-14538b46b077", "capsuleName": "Credit Amazon v2",
                  "clientControls": [{"id": "3", "type": 6, "uiName": {"strDB": [{"localeString": "de_DE", "str": "TextLayer"}]},
                                      "value": {"strDB": [{"localeString": "de_DE", "str": OLD}]}}],
                  "sourceInfoLocalized": {"de_DE": {"id": "73c0d1e6-46a9-464b-9c05-2d17e8bacd50"}}}
    xml = (f'<?xml version="1.0"?>\n<PremiereData><Sequence ObjectURef="73c0d1e6-46a9-464b-9c05-2d17e8bacd50"/><Media ObjectUID="11111111-2222-3333-4444-555555555555"/><Clip ObjectURef="11111111-2222-3333-4444-555555555555"/><Component><InstanceName>{OLD}</InstanceName></Component>\n'
           f'<ArbVideoComponentParam ObjectID="87"><Name>Quelltext</Name><StartKeyframeValue Encoding="base64" BinaryHash="94482de7-a436-2023-7605-57df000001ac">\n'
           f'{BLOB_B64}\n</StartKeyframeValue></ArbVideoComponentParam></PremiereData>')
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w", zipfile.ZIP_STORED) as z:
        z.writestr("Mythen - S2 E7_1_1.prproj", gzip.compress(xml.encode("utf-8")))
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("definition.json", json.dumps(definition, ensure_ascii=False))
        z.writestr("project.prgraphic", inner.getvalue())
        z.writestr("thumb.png", b"png")
    return path


def inspect(path: Path):
    with zipfile.ZipFile(path) as z:
        d = json.loads(z.read("definition.json"))
        inner = zipfile.ZipFile(io.BytesIO(z.read("project.prgraphic")))
        xml = gzip.decompress(inner.read(inner.namelist()[0])).decode("utf-8")
        thumb = z.read("thumb.png")
    blob = base64.b64decode(re.sub(r"\s", "", re.search(r"<StartKeyframeValue[^>]*>(.*?)</StartKeyframeValue>", xml, re.S).group(1)))
    return d, xml, blob, thumb


def test_make_text_mogrt_sets_text_everywhere_and_gives_a_fresh_identity(tmp_path, monkeypatch):
    monkeypatch.setattr(mogrt_text, "FRESH_SOURCE_ID", True)
    tpl = make_template(tmp_path / "Credit Amazon v2.mogrt")
    out = mogrt_text.make_text_mogrt(tpl, "© Alan & Lee <3 Ä", tmp_path / "out.mogrt")
    d, xml, blob, thumb = inspect(out)
    assert d["clientControls"][0]["value"]["strDB"][0]["str"] == "© Alan & Lee <3 Ä"
    assert read_text(blob) == "© Alan & Lee <3 Ä"
    assert "<InstanceName>© Alan &amp; Lee &lt;3 Ä</InstanceName>" in xml
    assert d["capsuleID"] != "ed2dd5ae-cb29-45ff-9380-14538b46b077"               # Premiere hält Vorlagen nach ihrer Kennung: sonst käme der Text der ersten
    new_id = d["sourceInfoLocalized"]["de_DE"]["id"]                                # Grafik-Kennung je Text neu, sonst behielte Premiere nur die erste Grafik
    assert new_id != "73c0d1e6-46a9-464b-9c05-2d17e8bacd50" and new_id in xml and "73c0d1e6" not in xml   # und im Projekt der Vorlage gleich
    assert thumb == b"png"
    # die Vorlage selbst bleibt unberührt
    assert read_text(inspect(tpl)[2]) == OLD


def test_text_mogrt_is_cached_per_text_and_template(tmp_path):
    tpl = make_template(tmp_path / "Credit Amazon v2.mogrt")
    a = mogrt_text.text_mogrt(tpl, "© A", tmp_path / "cache")
    b = mogrt_text.text_mogrt(tpl, "© A", tmp_path / "cache")
    c = mogrt_text.text_mogrt(tpl, "© B", tmp_path / "cache")
    assert a == b and a != c and a.exists() and c.exists()
    assert inspect(a)[0]["capsuleID"] == inspect(b)[0]["capsuleID"]


def test_all_object_ids_of_the_embedded_project_differ_per_text(tmp_path, monkeypatch):
    monkeypatch.setattr(mogrt_text, "FRESH_SOURCE_ID", True)
    tpl = make_template(tmp_path / "Credit Amazon v2.mogrt")
    a = inspect(mogrt_text.make_text_mogrt(tpl, "© A", tmp_path / "a.mogrt"))[1]
    b = inspect(mogrt_text.make_text_mogrt(tpl, "© B", tmp_path / "b.mogrt"))[1]
    ua, ub = set(mogrt_text._OBJECT_UID.findall(a)), set(mogrt_text._OBJECT_UID.findall(b))
    assert ua and ua.isdisjoint(ub) and "11111111-2222" not in a
    assert len(re.findall(r'ObjectURef="([^"]+)"', a)) == 2 and set(re.findall(r'ObjectURef="([^"]+)"', a)) <= ua | {inspect(tmp_path / "a.mogrt")[0]["sourceInfoLocalized"]["de_DE"]["id"]}   # Verweise zeigen auf die neuen Kennungen


def test_each_text_gets_its_own_graphic_identity(tmp_path, monkeypatch):
    monkeypatch.setattr(mogrt_text, "FRESH_SOURCE_ID", True)
    tpl = make_template(tmp_path / "Credit Amazon v2.mogrt")
    ids = {inspect(mogrt_text.text_mogrt(tpl, t, tmp_path / "c"))[0]["sourceInfoLocalized"]["de_DE"]["id"] for t in ("© A", "© B", "© C")}
    assert len(ids) == 3
    again = inspect(mogrt_text.make_text_mogrt(tpl, "© A", tmp_path / "again.mogrt"))[0]["sourceInfoLocalized"]["de_DE"]["id"]
    assert again in ids                                                              # stabil für denselben Text


def test_default_keeps_the_template_project_ids_and_only_renews_the_capsule_id(tmp_path):
    """Standard (wie in Premiere erprobt): nur capsuleID neu, Sequenz-Kennung und Objekte des eingebetteten Projekts wie in der Vorlage."""
    assert mogrt_text.FRESH_SOURCE_ID is False
    tpl = make_template(tmp_path / "Credit Amazon v2.mogrt")
    d, xml, blob, _ = inspect(mogrt_text.make_text_mogrt(tpl, "© A", tmp_path / "a.mogrt"))
    d0, xml0, _, _ = inspect(tpl)
    assert d["capsuleID"] != d0["capsuleID"] and read_text(blob) == "© A"
    assert d["sourceInfoLocalized"] == d0["sourceInfoLocalized"]
    assert set(mogrt_text._OBJECT_UID.findall(xml)) == set(mogrt_text._OBJECT_UID.findall(xml0))


def test_cache_key_contains_the_format_so_a_changed_layout_is_rebuilt(tmp_path, monkeypatch):
    """Gefunden in Test8–Test10: der Schlüssel enthielt die Formatkennung nicht, Änderungen am Aufbau erreichten Premiere nie."""
    tpl = make_template(tmp_path / "Credit Amazon v2.mogrt")
    a = mogrt_text.text_mogrt(tpl, "© A", tmp_path / "c")
    monkeypatch.setattr(mogrt_text, "FORMAT", b"99")
    b = mogrt_text.text_mogrt(tpl, "© A", tmp_path / "c")
    monkeypatch.setattr(mogrt_text, "FORMAT", b"3")
    monkeypatch.setattr(mogrt_text, "FRESH_SOURCE_ID", True)
    c = mogrt_text.text_mogrt(tpl, "© A", tmp_path / "c")
    assert len({a, b, c}) == 3


REAL = Path(__file__).resolve().parents[1] / "vorlagen" / "mogrt" / "Credit Amazon v2.mogrt"


@pytest.mark.skipif(not REAL.exists(), reason="echte Vorlage nur auf Dannys Rechner")
def test_real_template(tmp_path):
    out = mogrt_text.make_text_mogrt(REAL, "© Alan Lee", tmp_path / "x.mogrt")
    d, xml, blob, _ = inspect(out)
    assert read_text(blob) == "© Alan Lee" and d["clientControls"][0]["value"]["strDB"][0]["str"] == "© Alan Lee"
