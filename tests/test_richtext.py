import json
from pathlib import Path

import pytest

from glorfindel import richtext
from glorfindel.models import CommentBlock
from glorfindel.scenes import normalize_block

CASES = json.loads((Path(__file__).parent / "data" / "richtext_cases.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("c", CASES)
def test_plain(c):
    assert richtext.plain(c["markup"]) == c["plain"]


def test_has_markup():
    assert richtext.has_markup("das ist **fett**") and richtext.has_markup("- Punkt") and richtext.has_markup("a\n> b")
    assert not richtext.has_markup("Ganz normaler Text. Mit 2024 Zahlen – und Strichen.")


def test_formatted_comment_keeps_text_plain_and_mode():
    b = normalize_block(CommentBlock(markup="- erstens\n- zweitens", text="egal"))
    assert b.modus == "text" and b.text == "erstens\nzweitens" and b.markup == "- erstens\n- zweitens"   # Liste bleibt Text, wird nicht zu Stichpunkten
    b2 = normalize_block(CommentBlock(markup="Ein **Wort**", text="alt"))
    assert b2.text == "Ein Wort"
    b3 = normalize_block(CommentBlock(markup="Normal", text="Normal"))
    assert b3.markup == ""                                          # ohne Formatierung kein Markup speichern
