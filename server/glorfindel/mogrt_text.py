"""Credit-Vorlagen (.mogrt) mit festem Text.

Premiere lässt den Text einer eingesetzten Grafik per Skript weder lesen noch setzen (Premiere 27.1: Parameter „Quelltext“ liefert null).
Eine .mogrt ist aber ein ZIP: `definition.json` (freigegebenes Textfeld) und `project.prgraphic` (ZIP mit einem gzip-komprimierten
Premiere-Projekt, darin der Parameter „Quelltext“ als FlatBuffer-Block). Wir schreiben den Text dort hinein und geben der Vorlage eine neue Kennung;
das Panel setzt dann nur noch die fertige Datei ein."""
from __future__ import annotations

import base64
import gzip
import hashlib
import io
import json
import re
import struct
import uuid
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

HEADER = 12                                           # Kopf des Blocks: Länge des FlatBuffers (u32), 0, Kennung 0x11223344
_GUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def patch_text_blob(blob: bytes, old: str, new: str) -> bytes:
    """Text im Quelltext-Block ersetzen. Der neue String wird ans Ende gehängt und der eine Verweis darauf umgebogen:
    so verschiebt sich nichts, auf das andere Verweise zeigen. Der alte String bleibt als totes Gut stehen."""
    body = bytearray(blob[HEADER:])
    old_b = old.encode("utf-8")
    pos = bytes(body).find(struct.pack("<I", len(old_b)) + old_b + b"\0")
    if pos < 0:
        raise ValueError(f"Text „{old}“ steht nicht im Quelltext-Block der Vorlage")
    refs = [q for q in range(0, len(body) - 3, 4) if q != pos and q + struct.unpack_from("<I", body, q)[0] == pos]
    if len(refs) != 1:
        raise ValueError(f"Quelltext-Block hat einen unerwarteten Aufbau ({len(refs)} Verweise auf den Text)")
    new_b = new.encode("utf-8")
    body.extend(b"\0" * (-len(body) % 4))
    new_pos = len(body)
    body.extend(struct.pack("<I", len(new_b)) + new_b + b"\0")
    body.extend(b"\0" * (-len(body) % 4))
    struct.pack_into("<I", body, refs[0], new_pos - refs[0])
    head = bytearray(blob[:HEADER])
    struct.pack_into("<I", head, 0, len(body))
    return bytes(head) + bytes(body)


_PARAM = re.compile(r"(<Name>Quelltext</Name>.*?<StartKeyframeValue[^>]*>)(.*?)(</StartKeyframeValue>)", re.S)


def _patch_project(gz: bytes, old: str, new: str) -> bytes:
    xml = gzip.decompress(gz).decode("utf-8")
    m = _PARAM.search(xml)
    if not m:
        raise ValueError("Vorlage enthält keinen Parameter „Quelltext“")
    blob = base64.b64decode(re.sub(r"\s", "", m.group(2)))
    b64 = base64.b64encode(patch_text_blob(blob, old, new)).decode("ascii")
    xml = xml[:m.start(2)] + b64 + "\n\t\t" + xml[m.end(2):]
    xml = xml.replace(f"<InstanceName>{escape(old)}</InstanceName>", f"<InstanceName>{escape(new)}</InstanceName>")
    return gzip.compress(xml.encode("utf-8"), mtime=0)


def _fresh_ids(definition: dict) -> None:
    """Neue Kennung der Vorlage (capsuleID): Premiere hält Vorlagen nach ihrer Kennung.
    Die Quell-ID in sourceInfoLocalized bleibt: sie steht auch im Projekt der Vorlage, beide müssen übereinstimmen (sonst lässt sich die Datei nicht importieren)."""
    if isinstance(definition.get("capsuleID"), str) and _GUID.match(definition["capsuleID"]):
        definition["capsuleID"] = str(uuid.uuid4())


def make_text_mogrt(template: Path, text: str, dst: Path) -> Path:
    """Kopie der Vorlage mit anderem Text schreiben (atomar)."""
    with zipfile.ZipFile(template) as zin:
        definition = json.loads(zin.read("definition.json"))
        ctrl = next((c for c in definition.get("clientControls", []) if c.get("type") == 6), None)
        if ctrl is None:
            raise ValueError("Vorlage hat kein freigegebenes Textfeld")
        entries = ctrl["value"]["strDB"]
        old = entries[0]["str"]
        for e in entries:
            e["str"] = text
        _fresh_ids(definition)
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
            for info in zin.infolist():
                data = zin.read(info.filename)
                if info.filename == "definition.json":
                    data = json.dumps(definition, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                elif info.filename == "project.prgraphic":
                    inner_in = zipfile.ZipFile(io.BytesIO(data))
                    inner_out = io.BytesIO()
                    with zipfile.ZipFile(inner_out, "w", zipfile.ZIP_STORED) as zi:
                        for ii in inner_in.infolist():
                            blob = inner_in.read(ii.filename)
                            zi.writestr(ii.filename, _patch_project(blob, old, text) if ii.filename.lower().endswith(".prproj") else blob)
                    data = inner_out.getvalue()
                zout.writestr(info.filename, data)
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(".part")
    tmp.write_bytes(out.getvalue())
    tmp.replace(dst)
    return dst


def text_mogrt(template: Path, text: str, folder: Path) -> Path:
    """Vorlage mit festem Text, je Vorlage und Text nur einmal erzeugt."""
    key = hashlib.sha1(Path(template).read_bytes() + b"\0" + text.encode("utf-8")).hexdigest()[:12]
    dst = Path(folder) / f"{Path(template).stem} {key}.mogrt"
    return dst if dst.exists() else make_text_mogrt(Path(template), text, dst)
