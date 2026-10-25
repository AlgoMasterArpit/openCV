from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ReadingStatus(StrEnum):
    SAVED = "saved"
    BASELINE = "baseline"
    NEEDS_REVIEW = "needs_review"


class ReadingRecord(BaseModel):
    hostel_id: str
    room_id: str
    round_id: str
    recorded_at: str
    status: ReadingStatus
    meter_type: str
    reading: str | None = None
    serial: str | None = None
    units: int | None = None
    unit_label: str | None = None
    co2_kg: float | None = None
    reason: str | None = None
    session_id: str
    photo_keys: list[str] = Field(default_factory=list)
    trace: list[dict[str, Any]] = Field(default_factory=list)
    location: str | None = None

    @property
    def counts_as_reading(self) -> bool:
        return self.status in (ReadingStatus.SAVED, ReadingStatus.BASELINE)
