from __future__ import annotations

from app.agent.summary import summarize
from app.domain.factors import co2_kg
from app.domain.units import consumption, went_backwards


def test_consumption() -> None:
    assert consumption("01890", "01910") == 20
    assert consumption(None, "01910") is None
    assert consumption("01950", "01910") is None
    assert went_backwards("01950", "01910")
    assert not went_backwards(None, "01910")


def test_co2_only_where_a_factor_exists() -> None:
    assert co2_kg("electricity", 20) == 14.54
    assert co2_kg("water", 20) is None
    assert co2_kg("electricity", None) is None


def test_summary_reads_like_the_demo() -> None:
    trace = [
        {"photo": 1, "step": "perceive", "quality": ["glare"]},
        {
            "photo": 1,
            "step": "decide",
            "action": "retake",
            "reason": "bad_photo",
            "decided_by": "llm",
        },
        {"photo": 2, "step": "perceive", "quality": []},
        {
            "photo": 2,
            "step": "decide",
            "action": "retake",
            "reason": "mismatch",
            "decided_by": "rule",
        },
        {"photo": 3, "step": "perceive", "quality": []},
        {
            "photo": 3,
            "step": "decide",
            "action": "reread",
            "reason": "unclear_digit",
            "decided_by": "rule",
        },
        {"photo": 3, "step": "reread", "variant": "clahe"},
        {
            "photo": 3,
            "step": "decide",
            "action": "save",
            "reason": "clear_reading",
            "decided_by": "rule",
        },
    ]
    assert [line["label"] for line in summarize(trace)] == [
        "Glare: retake",
        "Galat meter pakda",
        "Digit dobara padha",
        "Reading save",
    ]
    assert summarize(trace)[0]["decided_by"] == "llm"
