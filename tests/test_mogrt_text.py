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
    xml = (f'<?xml version="1.0"?>\n<PremiereData><Component><InstanceName>{OLD}</InstanceName></Component>\n'
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


def test_make_text_mogrt_sets_text_everywhere_and_gives_a_fresh_identity(tmp_path):
    tpl = make_template(tmp_path / "Credit Amazon v2.mogrt")
    out = mogrt_text.make_text_mogrt(tpl, "© Alan & Lee <3 Ä", tmp_path / "out.mogrt")
    d, xml, blob, thumb = inspect(out)
    assert d["clientControls"][0]["value"]["strDB"][0]["str"] == "© Alan & Lee <3 Ä"
    assert read_text(blob) == "© Alan & Lee <3 Ä"
    assert "<InstanceName>© Alan &amp; Lee &lt;3 Ä</InstanceName>" in xml
    assert d["capsuleID"] != "ed2dd5ae-cb29-45ff-9380-14538b46b077"               # Premiere hält Vorlagen nach ihrer Kennung: sonst käme der Text der ersten
    assert d["sourceInfoLocalized"]["de_DE"]["id"] == "73c0d1e6-46a9-464b-9c05-2d17e8bacd50"   # steht auch im Projekt der Vorlage: muss übereinstimmen
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


REAL = Path(__file__).resolve().parents[1] / "vorlagen" / "mogrt" / "Credit Amazon v2.mogrt"


@pytest.mark.skipif(not REAL.exists(), reason="echte Vorlage nur auf Dannys Rechner")
def test_real_template(tmp_path):
    out = mogrt_text.make_text_mogrt(REAL, "© Alan Lee", tmp_path / "x.mogrt")
    d, xml, blob, _ = inspect(out)
    assert read_text(blob) == "© Alan Lee" and d["clientControls"][0]["value"]["strDB"][0]["str"] == "© Alan Lee"
