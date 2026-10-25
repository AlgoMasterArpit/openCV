from __future__ import annotations


def consumption(previous: str | None, current: str) -> int | None:
    """Units since the previous reading; None without a previous one or if it went backwards."""
    if previous is None or not previous.isdigit() or not current.isdigit():
        return None
    used = int(current) - int(previous)
    return used if used >= 0 else None


def went_backwards(previous: str | None, current: str) -> bool:
    return bool(
        previous and previous.isdigit() and current.isdigit() and int(current) < int(previous)
    )
