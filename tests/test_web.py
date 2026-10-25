"""Die Weboberfläche: alle importierten Module existieren und werden ausgeliefert."""
import re
from pathlib import Path

from fastapi.testclient import TestClient

from glorfindel.api import WEB_DIR, create_app


def test_all_js_imports_resolve():
    for f in WEB_DIR.glob("js/**/*.js"):
        for m in re.finditer(r"(?:from|import\()\s*'(\.[^']+\.js)'", f.read_text(encoding="utf-8")):
            assert (f.parent / m.group(1)).resolve().exists(), f"{f.name}: {m.group(1)} fehlt"


def test_index_and_static_served(tmp_path, monkeypatch):
    monkeypatch.setenv("GLORFINDEL_HOME", str(tmp_path))
    c = TestClient(create_app())
    assert "main.js" in c.get("/").text
    assert c.get("/static/js/main.js").status_code == 200
    assert c.get("/static/js/views/editor.js").status_code == 200


def test_panel_skeleton_is_valid_json():
    import json
    root = Path(__file__).resolve().parents[1] / "premiere-panel"
    m = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    assert m["manifestVersion"] == 5 and m["host"]["app"] == "premierepro"
    assert "Bridge" in (root / "main.js").read_text(encoding="utf-8") and (root / "lib" / "plan.js").exists()


def test_help_guide_served_and_complete(tmp_path, monkeypatch):
    monkeypatch.setenv("GLORFINDEL_HOME", str(tmp_path))
    c = TestClient(create_app())
    r = c.get("/static/help/anleitung.md")
    assert r.status_code == 200
    for must in ("Installation", "Szenen-Editor", "Aufnahme", "Rohschnitt", "Tastenkürzel", "Probleme und Lösungen"):
        assert must in r.text


def test_help_images_exist():
    import re
    help_dir = WEB_DIR / "help"
    imgs = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", (help_dir / "anleitung.md").read_text(encoding="utf-8"))
    assert len(imgs) >= 10
    for i in imgs:
        assert (help_dir / i).is_file(), f"Bild fehlt: {i}"


def test_premiere_effects_endpoint_lists_library(tmp_path, monkeypatch):
    monkeypatch.setenv("GLORFINDEL_HOME", str(tmp_path))
    c = TestClient(create_app())
    r = c.get("/api/premiere/effects")
    assert r.status_code == 200
    ids = {e["id"] for e in r.json()["effekte"]}
    assert {"drop_shadow", "fancy_in", "fancy_out", "zoom_schnell", "zoom_langsam", "karte_in", "karte_out"} <= ids
