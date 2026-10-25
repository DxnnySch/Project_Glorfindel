from types import SimpleNamespace

import pytest
from PIL import Image

from glorfindel import maps, media
from glorfindel.config import Settings
from glorfindel.llm import Llm

from conftest import needs_ffmpeg


def sample_map():
    m = maps.new_map("k_eregion", "Karten/test.png", dauer=2.0)
    m["hinweise"] = "Heerzug der Orks in Rot"
    m["elemente"] = [
        {"typ": "marker", "x": 0.3, "y": 0.4, "text": "Ost-in-Edhil", "hinweis": "hier Schmiede"},
        {"typ": "pfeil", "punkte": [[0.3, 0.4], [0.6, 0.5], [0.8, 0.3]], "t0": 0.2, "dauer": 1.0},
        {"typ": "region", "punkte": [[0.1, 0.1], [0.3, 0.1], [0.2, 0.3]], "text": "Eregion"},
    ]
    m["kamera"] = [{"t": 0, "rect": [0, 0, 1, 1]}, {"t": 2.0, "rect": [0.2, 0.2, 0.4, 0.4]}]
    return m


@pytest.fixture
def map_img(tmp_path):
    p = tmp_path / "karte.png"
    Image.new("RGB", (1200, 800), (90, 120, 80)).save(p)
    return p


def test_camera_interpolation_and_path_progress():
    m = sample_map()
    assert maps.camera_rect(m, -1) == [0, 0, 1, 1]
    assert maps.camera_rect(m, 2.0) == pytest.approx([0.2, 0.2, 0.4, 0.4])
    mid = maps.camera_rect(m, 1.0)
    assert 0.0 < mid[0] < 0.2 and mid[0] == pytest.approx(0.1)  # smoothstep(0.5) = 0.5
    p = maps._path_progress([[0, 0], [1, 0], [1, 1]], 0.5)
    assert p[-1] == pytest.approx((1.0, 0.0)) and len(p) == 2
    assert maps._path_progress([[0, 0], [1, 0]], 1.0) == [(0, 0), (1, 0)]


def test_list_and_thumbnail(tmp_path, map_img):
    assert [x["name"] for x in maps.list_maps(tmp_path, "karte")] == ["karte.png"]
    assert maps.list_maps(tmp_path, "zzz") == []
    th = maps.thumbnail(map_img, tmp_path / "t" / "k.jpg", 100)
    assert max(Image.open(th).size) == 100


def test_sheet_png_and_pdf(tmp_path, map_img):
    png = maps.render_sheet(sample_map(), map_img, tmp_path / "s.png")
    im = Image.open(png)
    assert im.height > 800 * (im.width / 1200)  # Hinweis-Panel angehängt
    pdf = maps.render_sheet(sample_map(), map_img, tmp_path / "s.pdf")
    assert pdf.read_bytes()[:4] == b"%PDF"


@needs_ffmpeg
def test_placeholder_clip(tmp_path, map_img):
    out = maps.render_placeholder_clip(sample_map(), map_img, tmp_path / "p.mp4", fps=12, size=(640, 267))
    info = media.probe(out)
    assert info["duration"] == pytest.approx(2.0, abs=0.2) and info["width"] == 640


# ---- LLM mit Fake-Client (offline) ----
class FakeClient:
    def __init__(self, reply):
        self.reply, self.calls = reply, []
        self.models = SimpleNamespace(list=lambda: SimpleNamespace(data=[SimpleNamespace(id="zai-org/GLM-5.3-Flash"),
                                                                            SimpleNamespace(id="zai-org/GLM-5.3")]))
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.calls.append(kw)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self.reply))])


def llm(reply, **feat):
    s = Settings()
    s.llm.features.update(feat)
    return Llm(s, client=FakeClient(reply))


def test_llm_model_choice_and_json():
    l = llm('<think>x</think>[{"falsch": "Galadrijel", "richtig": "Galadriel"}]')
    assert l.model_for("name_check") == "zai-org/GLM-5.3-Flash" and l.model_for("map_suggest") == "zai-org/GLM-5.3"
    assert l.check_names("Galadrijel")[0]["richtig"] == "Galadriel"


def test_llm_fix_transcript_guards_wordcount():
    assert llm("Celebrimbor schmiedet Ringe").fix_transcript("Selebrimbor schmiedet Ringe", "g") == "Celebrimbor schmiedet Ringe"
    # Modell erfindet Text -> Original bleibt
    assert llm("Celebrimbor schmiedet viele neue wunderschöne Ringe in der Schmiede").fix_transcript("a b c", "g") == "a b c"


def test_llm_feature_toggle_and_failure():
    l = llm("x", name_check=False)
    assert l.check_names("t") == [] and l.client.calls == []

    class Boom(FakeClient):
        def _create(self, **kw):
            raise RuntimeError("500")
    s = Settings()
    assert Llm(s, client=Boom("")).suggest_search_terms("Text") == []


def test_llm_map_suggest_validates_choice():
    assert llm('{"karte": "A", "orte": ["x"]}').suggest_map("t", ["A", "B"])["karte"] == "A"
    assert llm('{"karte": "Z", "orte": []}').suggest_map("t", ["A", "B"]) is None


def test_element_end_time_hides_with_fade(map_img):
    from PIL import ImageChops
    m = maps.new_map("k", "x.png", dauer=3.0)
    m["elemente"] = [{"typ": "marker", "x": 0.5, "y": 0.5, "text": "", "t0": 0.5, "t1": 1.5}]
    base = Image.new("RGB", (400, 300), (40, 40, 40))

    def at(t):
        return maps.draw_elements(base.copy().convert("RGBA"), m, t=t)

    def changed(im):
        return ImageChops.difference(im.convert("RGB"), base).getbbox() is not None

    assert not changed(at(0.2)) and changed(at(1.0))                # vor dem Start unsichtbar, danach sichtbar
    assert changed(at(1.6))                                         # kurzes Ausblenden
    assert not changed(at(2.0))                                     # nach Ende + Ausblenden weg
