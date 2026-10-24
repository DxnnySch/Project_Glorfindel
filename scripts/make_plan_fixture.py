"""Schreibt premiere-panel/test/fixtures/plan.json neu (nach Änderungen am Plan-Builder ausführen)."""
import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root / "server"), str(root / "tests")]
from plan_fixture import FIXTURE, make_plan  # noqa: E402

FIXTURE.parent.mkdir(parents=True, exist_ok=True)
FIXTURE.write_text(json.dumps(make_plan(), ensure_ascii=False, indent=1), encoding="utf-8")
print("geschrieben:", FIXTURE)
