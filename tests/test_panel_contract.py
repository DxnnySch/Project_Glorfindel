"""Vertrag Python-Plan ↔ JS-Panel: Die Testdatei des Panels stammt aus dem echten Plan-Builder; die JS-Tests laufen hier mit."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from plan_fixture import FIXTURE, make_plan

ROOT = Path(__file__).resolve().parents[1]


def test_panel_fixture_is_current():
    """Ändert sich der Plan-Builder, muss `python scripts/make_plan_fixture.py` laufen – sonst testet das Panel veraltete Pläne."""
    assert json.loads(FIXTURE.read_text(encoding="utf-8")) == make_plan(), "Fixture veraltet: python scripts/make_plan_fixture.py"


@pytest.mark.skipif(not shutil.which("node"), reason="Node.js nicht installiert")
def test_panel_javascript_tests_pass():
    r = subprocess.run(["node", "--test", str(ROOT / "premiere-panel" / "test" / "panel.test.js")], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-1500:]


def test_manifest_is_valid_for_premiere():
    m = json.loads((ROOT / "premiere-panel" / "manifest.json").read_text(encoding="utf-8"))
    assert m["host"]["app"] == "premierepro" and m["main"] == "index.html" and m["entrypoints"][0]["type"] == "panel"
    assert (ROOT / "premiere-panel" / m["main"]).exists()
    assert m["requiredPermissions"]["network"]["domains"] == "all"
    for f in ("lib/core.js", "lib/plan.js", "lib/bridge.js", "main.js"):
        assert (ROOT / "premiere-panel" / f).exists()


def test_websocket_library_is_a_runtime_dependency():
    """uvicorn nimmt WebSocket-Verbindungen nur mit `websockets` an – ohne sie würde sich das Panel nie verbinden."""
    toml = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    deps = toml[toml.index("dependencies"):toml.index("[project.optional")]
    assert "websockets" in deps
    import websockets  # noqa: F401


def test_panel_version_matches_manifest():
    import json
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent / "premiere-panel"
    version = json.loads((root / "manifest.json").read_text(encoding="utf-8"))["version"]
    assert f"const VERSION = '{version}'" in (root / "main.js").read_text(encoding="utf-8")
    assert re.search(rf"version = '{re.escape(version)}'", (root / "lib" / "bridge.js").read_text(encoding="utf-8"))
