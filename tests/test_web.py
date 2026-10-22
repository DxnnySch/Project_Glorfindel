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
