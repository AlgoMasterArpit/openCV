from __future__ import annotations

from typing import Any

QUALITY_LABELS = {"glare": "Glare", "blur": "Dhundhli photo", "dark": "Andhera"}

ACTION_LABELS = {
    ("retake", "mismatch"): "Galat meter pakda",
    ("retake", "unreadable_serial"): "Serial nahi padha: retake",
    ("new_photo", "unclear_photos"): "Digit unclear: nayi photo",
    ("review", "backwards"): "Reading pichhli se kam: review",
    ("retake", "caretaker_said_no"): "Caretaker ne mana kiya: retake",
}


def _label(step: dict[str, Any], quality: list[str]) -> str | None:
    kind = step["step"]
    if kind == "reread":
        return "Digit dobara padha"
    if kind != "decide":
        return None
    action, reason = step["action"], step.get("reason", "")
    if action == "reread":
        return None
    if (action, reason) in ACTION_LABELS:
        return ACTION_LABELS[(action, reason)]
    if action == "retake":
        issue = next((QUALITY_LABELS[q] for q in quality if q in QUALITY_LABELS), None)
        return f"{issue}: retake" if issue else "Display nahi dikha: retake"
    return {
        "save": "Reading save",
        "review": "Review mein bheja",
        "confirm": "Serial aur reading padhi",
        "linked": "Meter joda",
    }.get(action)


def summarize(trace: list[dict[str, Any]]) -> list[dict[str, str]]:
    """The short 'Agent ne kya kiya' list shown on the caretaker's screen."""
    quality: dict[int, list[str]] = {}
    lines = []
    for step in trace:
        photo = int(step.get("photo", 0))
        if step["step"] == "perceive":
            quality[photo] = list(step.get("quality", []))
            continue
        label = _label(step, quality.get(photo, []))
        if label:
            by = str(step.get("decided_by", "opencv"))
            lines.append({"label": label, "decided_by": "rule" if by.startswith("rule") else by})
    return lines
