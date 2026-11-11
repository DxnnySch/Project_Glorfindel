import subprocess
from pathlib import Path

import pytest

from glorfindel import images, prfpset
from glorfindel.detect import detect_shots, detect_silences, propose_scenes, thumbnails

from conftest import needs_ffmpeg

REAL_PRESETS = Path("F:/OneDrive/Videomaterial/Programm-Vorgaben/PremierePro")

XMP = """<?xpacket begin='' id='W5M0MpCehiHzreSzNTczkc9d'?>
<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
<rdf:Description xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:lr="http://ns.adobe.com/lightroom/1.0/">
<dc:subject><rdf:Bag><rdf:li>Celebrimbor</rdf:li><rdf:li>Schmiede</rdf:li></rdf:Bag></dc:subject>
<lr:hierarchicalSubject><rdf:Bag><rdf:li>Figuren|Elben|Celebrimbor</rdf:li></rdf:Bag></lr:hierarchicalSubject>
<dc:title><rdf:Alt><rdf:li xml:lang="x-default">Der Schmied</rdf:li></rdf:Alt></dc:title>
<dc:description><rdf:Alt><rdf:li xml:lang="x-default">Celebrimbor am Amboss</rdf:li></rdf:Alt></dc:description>
<dc:creator><rdf:Seq><rdf:li>Alan Lee</rdf:li></rdf:Seq></dc:creator>
</rdf:Description></rdf:RDF></x:xmpmeta><?xpacket end='w'?>"""


def test_parse_xmp_packet():
    m = images.parse_xmp_packet(XMP[XMP.index("<x:xmpmeta"):XMP.index("</x:xmpmeta>") + 12])
    assert m["keywords"] == ["Celebrimbor", "Schmiede", "Figuren", "Elben"]
    assert m["title"] == "Der Schmied" and m["creator"] == "Alan Lee" and "Amboss" in m["description"]


def test_xxe_is_rejected(tmp_path):
    evil = ('<?xml version="1.0"?><!DOCTYPE x [<!ENTITY e SYSTEM "file:///etc/passwd">]>'
            '<x:xmpmeta xmlns:x="adobe:ns:meta/">&e;</x:xmpmeta>')
    with pytest.raises(Exception):
        images.parse_xmp_packet(evil)


def make_img(path, color=(200, 30, 30)):
    from PIL import Image
    im = Image.new("RGB", (200, 120), color)
    im.paste((10, 10, 10), (60, 30, 140, 90))   # dunkle Mitte
    im.save(path)


def test_index_and_search_with_sidecar(tmp_path):
    root = tmp_path / "OD"
    d = root / "Bilder"
    d.mkdir(parents=True)
    make_img(d / "alan lee - schmiede 1.jpg")
    make_img(d / "john howe.png")
    (d / "alan lee - schmiede 1.xmp").write_text(XMP, encoding="utf-8")
    idx = images.ImageIndex(tmp_path / "idx.db")
    assert idx.index_folder(root, d) == {"added": 2, "unchanged": 0}
    assert idx.index_folder(root, d)["unchanged"] == 2
    r = idx.search("celebrimbor")
    assert [x["path"] for x in r] == ["Bilder/alan lee - schmiede 1.jpg"]
    assert idx.search("howe")[0]["path"].endswith("john howe.png")
    assert idx.search(tags=["Elben"])[0]["creator"] == "Alan Lee"
    assert ("Celebrimbor", 1) in idx.all_keywords()
    assert idx.search("nichtda") == []


def test_default_credit_priority():
    meta = {"creator": "Ted Nasmith"}
    assert images.default_credit("Bilder/Alan Lee - 3.jpg", meta, {"alan lee": "alan lee (ar)"}) == "alan lee (ar)"
    assert images.default_credit("Bilder/x_1.jpg", meta) == "ted nasmith"
    assert images.default_credit("Bilder/john howe 2.jpg") == "john howe"


def test_dominant_edge_color_ignores_dark_center(tmp_path):
    p = tmp_path / "a.png"
    make_img(p, (200, 30, 30))
    c = images.dominant_edge_color(p)
    r, g, b = (int(c[i:i + 2], 16) for i in (1, 3, 5))
    assert r > 150 and g < 80 and b < 80


@needs_ffmpeg
def test_contour_color_animated(tmp_path):
    p = tmp_path / "w.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=0x2060c0:s=160x90:d=2:r=10",
                    "-pix_fmt", "yuv420p", str(p)], check=True)
    c = images.contour_color(p)
    r, g, b = (int(c[i:i + 2], 16) for i in (1, 3, 5))
    assert b > r and b > 120


PUBLIC = lambda host: ["93.184.216.34"]


def test_web_import_validations(tmp_path):
    import httpx
    png = tmp_path / "x.png"
    make_img(png)

    def handler(req):
        if req.url.path.endswith("page"):
            return httpx.Response(200, text="<html>", headers={"content-type": "text/html"})
        return httpx.Response(200, content=png.read_bytes(), headers={"content-type": "image/png"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    r = images.web_import("https://example.org/a/Bild%20X.png", tmp_path / "assets", client, resolver=PUBLIC)
    assert r["path"].exists() and r["source_url"].startswith("https://") and r["path"].suffix == ".png"
    r2 = images.web_import("https://example.org/a/Bild%20X.png", tmp_path / "assets", client, resolver=PUBLIC)
    assert r2["path"] != r["path"]
    with pytest.raises(ValueError):
        images.web_import("https://example.org/page", tmp_path / "assets", client, resolver=PUBLIC)
    with pytest.raises(ValueError):
        images.web_import("file:///etc/passwd", tmp_path / "assets", client, resolver=PUBLIC)


@pytest.mark.parametrize("url,addr", [
    ("http://localhost/x.png", "127.0.0.1"), ("http://intranet.local/x.png", "192.168.1.5"),
    ("http://169.254.169.254/latest/meta-data", None), ("http://10.0.0.1/a.png", None),
    ("http://[::1]/a.png", None), ("http://evil.example/x.png", "10.1.2.3"),
])
def test_web_import_blocks_non_public_targets(tmp_path, url, addr):
    with pytest.raises(ValueError):
        images.web_import(url, tmp_path / "a", resolver=lambda h: [addr or h])


def test_web_import_rechecks_redirect_hops(tmp_path):
    import httpx

    def handler(req):
        if req.url.host == "good.example":
            return httpx.Response(302, headers={"location": "http://metadata.internal/x.png"})
        return httpx.Response(200, content=b"x", headers={"content-type": "image/png"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    resolver = lambda h: ["10.0.0.7"] if h == "metadata.internal" else ["93.184.216.34"]
    with pytest.raises(ValueError, match="öffentliche"):
        images.web_import("https://good.example/a.png", tmp_path / "a", client, resolver=resolver)


# ---- prfpset ----
@pytest.mark.skipif(not REAL_PRESETS.exists(), reason="echte Vorgaben nicht verfügbar")
def test_real_prfpset_recipes():
    rec = prfpset.import_folder(REAL_PRESETS)
    fi, fo, gi, go = rec["Fancy In"], rec["Fancy Out"], rec["Gauß In"], rec["Gauß Out"]
    assert fi["effect"] == "AE.ADBE Roughen Edges" and fi["anchor"] == "start"
    assert fi["keyframes"]["Rahmen"] == [[0.0, 500], [0.5, 8]]
    assert fi["keyframes"]["Skalieren"][0] == [0.0, 204]
    assert fo["anchor"] == "end" and -0.05 <= fo["keyframes"]["Rahmen"][-1][0] <= 0.0 and fo["keyframes"]["Rahmen"][0][0] < 0
    assert gi["anchor"] == "start" and go["anchor"] == "end"
    assert not any("error" in v for v in rec.values())


# ---- Szenenerkennung ----
@needs_ffmpeg
def test_detect_shots_scenes_and_thumbs(tmp_path):
    parts = []
    for i, c in enumerate(["red", "blue", "green", "yellow"]):
        p = tmp_path / f"p{i}.mp4"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c={c}:s=160x90:d=3:r=24",
                        "-f", "lavfi", "-i", "sine=frequency=300:duration=3", "-shortest", "-pix_fmt", "yuv420p", str(p)],
                       check=True)
        parts.append(p)
    lst = tmp_path / "l.txt"
    lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts))
    vid = tmp_path / "all.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", str(vid)], check=True)
    shots = detect_shots(vid)
    assert len(shots) == 4 and shots[1][0] == pytest.approx(3.0, abs=0.1)
    sc = propose_scenes(shots, [], min_len=5.0)
    assert len(sc) >= 1 and sc[0]["start"] == 0 and sc[-1]["end"] == pytest.approx(12.0, abs=0.2)
    assert propose_scenes(shots, [(2.9, 3.2)], min_len=2.0)[1]["start"] == pytest.approx(3.0, abs=0.1)
    assert detect_silences(vid) == [] or isinstance(detect_silences(vid), list)
    th = thumbnails(vid, [0.5, 4.0], tmp_path / "th")
    assert all(t.exists() for t in th)


@needs_ffmpeg
@pytest.mark.parametrize("dur", [0.5, 1.5])
def test_detect_shots_finds_start_of_soft_dissolve(tmp_path, dur):
    """Weiche Blende: ContentDetector allein verpasst sie (lange Blende) oder meldet ihr Ende (kurze Blende)."""
    vid = tmp_path / "x.mp4"
    flt = (f"testsrc2=s=320x180:r=24:d=6[a];smptebars=s=320x180:r=24:d=6[b];"
           f"[a][b]xfade=transition=fade:duration={dur}:offset=4.5,format=yuv420p")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-filter_complex", flt, "-t", "10", str(vid)], check=True)
    starts = [a for a, _ in detect_shots(vid)][1:]
    assert len(starts) == 1 and starts[0] == pytest.approx(4.5, abs=0.2)
    assert [a for a, _ in detect_shots(vid, dissolves=False)][1:] != starts   # belegt den Fehler ohne Blendendetektor
