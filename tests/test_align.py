from glorfindel.align import (align_block, align_recording, find_takes, norm, norm_words,
                              pick_whisper_model)


def words_at(text: str, t0: float, step: float = 0.4):
    return [{"w": w, "start": round(t0 + i * step, 3), "end": round(t0 + i * step + step * 0.9, 3)}
            for i, w in enumerate(text.split())]


SCRIPT_A = "Celebrimbor schmiedet in Ost-in-Edhil die ersten Ringe der Macht"
SCRIPT_B = "Das passt gut zu dem was Tolkien im Silmarillion über Annatar schreibt"


def transcript():
    tr = []
    tr += words_at("äh also wir fangen an", 0)
    # Retake 1 von A (mit Versprecher), dann Retake 2 (sauber)
    tr += words_at("Celebrimbor schmiedet in Ost-in-Edhil die ersten Ringe der", 5.0)
    tr += words_at("Celebrimbor schmiedet in Ost-in-Edhil die ersten Ringe der Macht", 12.0)
    tr += words_at("Das passt gut zu dem was Tolkien im Silmarillion also über Annatar schreibt", 25.0)
    return tr


def test_normalization():
    assert norm("Khazad-dûm,") == "khazaddum" and norm("Größe") == "grosse"
    assert norm_words("Ost-in-Edhil, die!") == ["ostinedhil", "die"]


def test_find_takes_detects_retakes():
    tr = transcript()
    takes = find_takes(norm_words(SCRIPT_A), [norm(w["w"]) for w in tr])
    assert len(takes) >= 2


def test_last_take_default_and_switchable():
    tr = transcript()
    last = align_block(SCRIPT_A, tr)
    first = align_block(SCRIPT_A, tr, prefer="best")
    assert last is not None and last["in"] >= 11.5          # zweiter Take bei 12 s
    assert last["chosen"] == len(last["takes"]) - 1
    assert len(last["takes"]) >= 2 and last["confidence"] > 0.9
    assert first["confidence"] >= last["confidence"] - 1e-9


def test_spontaneous_additions_and_word_times():
    tr = transcript()
    r = align_block(SCRIPT_B, tr)
    assert r["in"] <= 25.0 and r["out"] > 25 + 0.4 * 11
    assert any("also" in e for e in r["ergaenzungen"])
    w = {x["i"]: x for x in r["words"]}
    assert len(w) == len(norm_words(SCRIPT_B))
    assert w[0]["start"] == 25.0 and w[0]["start"] < w[8]["start"] < w[len(w) - 1]["start"]


def test_no_match_returns_none():
    assert align_block("völlig anderer Text über Hobbits und Pfeifenkraut im Auenland", transcript()) is None


def test_align_recording_collects_missing_and_scenes():
    res = align_recording([("sz_01", 0, SCRIPT_A), ("sz_02", 0, SCRIPT_B),
                           ("sz_03", 0, "Kein Treffer hier irgendwo nirgendwo mehr")], transcript(), "r1")
    assert res["sz_01"][0]["rec"] == "r1" and not res["sz_01"][0].get("missing")
    assert res["sz_03"][0]["missing"] is True


def test_whisper_model_choice_explicit():
    assert pick_whisper_model("medium")[0] == "medium"
