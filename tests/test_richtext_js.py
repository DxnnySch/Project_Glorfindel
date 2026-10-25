"""Die JavaScript-Fassung des formatierten Kommentars liefert dieselben Ergebnisse wie die Python-Fassung (gleiche Testfälle)."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="Node nicht installiert")

CASES = ROOT / "tests" / "data" / "richtext_cases.json"


def run(script: Path) -> str:
    r = subprocess.run(["node", str(script)], capture_output=True, cwd=ROOT)
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")
    return r.stdout.decode("utf-8")


def test_js_plain_matches_python_cases(tmp_path):
    script = tmp_path / "t.mjs"
    script.write_text(
        "import fs from 'node:fs';\n"
        f"import * as m from {json.dumps((ROOT / 'web' / 'js' / 'richtextcore.js').as_uri())};\n"
        f"const c = JSON.parse(fs.readFileSync({json.dumps(str(CASES))}, 'utf8'));\n"
        "process.stdout.write(Buffer.from(JSON.stringify(c.map((x) => m.plain(x.markup))), 'utf8'));\n", encoding="utf-8")
    assert json.loads(run(script)) == [c["plain"] for c in json.loads(CASES.read_text(encoding="utf-8"))]


def test_js_word_tokens_map_back_into_markup(tmp_path):
    markup = "Das ist **sehr [wichtig]{#ff0000}** und\n- Punkt"
    script = tmp_path / "t.mjs"
    script.write_text(
        f"import * as m from {json.dumps((ROOT / 'web' / 'js' / 'richtextcore.js').as_uri())};\n"
        f"const s = {json.dumps(markup)};\n"
        "const t = m.wordTokens(s);\n"
        "console.log(JSON.stringify({ words: t.map((x) => x.word), spans: t.map((x) => s.slice(x.start, x.end)) }));\n", encoding="utf-8")
    out = json.loads(run(script))
    assert out["words"] == ["Das", "ist", "sehr", "wichtig", "und", "Punkt"]
    assert out["spans"] == ["Das", "ist", "sehr", "wichtig", "und", "Punkt"]
