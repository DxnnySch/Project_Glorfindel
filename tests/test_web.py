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
    assert "Rohschnitt" in (root / "main.js").read_text(encoding="utf-8")


def test_help_guide_served_and_complete(tmp_path, monkeypatch):
    monkeypatch.setenv("GLORFINDEL_HOME", str(tmp_path))
    c = TestClient(create_app())
    r = c.get("/static/help/anleitung.md")
    assert r.status_code == 200
    for must in ("Installation", "Szenen-Editor", "Aufnahme", "Rohschnitt", "Tastenkürzel", "Probleme und Lösungen"):
        assert must in r.text
