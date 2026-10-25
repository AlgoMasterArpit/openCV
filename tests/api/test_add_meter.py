from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.store.table import Table
from tests.api.test_photos import jpeg, send, session
from tests.vision import synth

pytestmark = pytest.mark.usefixtures("models_ready")


def meter_photo(serial: str = "SN 48217", reading: str = "01910") -> bytes:
    return jpeg(synth.meter_photo(reading, serial=serial))


def confirm(client: TestClient, sid: str, answer: str = "yes") -> Any:
    return client.post(f"/api/sessions/{sid}/confirm", json={"answer": answer}).json()


def test_photo_then_confirm_links_meter_with_baseline(client: TestClient, table: Table) -> None:
    sid = session(client, "205")
    body = send(client, sid, meter_photo())
    assert body["action"] == "confirm"
    assert body["confirm"] == {"serial": "48217", "serial_last4": "8217", "reading": "01910"}
    assert table.get_room("hostel-a", "205").meter_serial is None  # type: ignore[union-attr]

    linked = confirm(client, sid)
    assert linked["saved"]["status"] == "baseline"
    assert linked["summary"][-1]["label"] == "Meter joda"
    room = table.get_room("hostel-a", "205")
    assert room is not None
    assert (room.meter_serial, room.previous_reading) == ("48217", "01910")
    assert table.meter_owner("48217") == "205"
    rooms = {r["room_id"]: r for r in client.get("/api/round").json()["rooms"]}
    assert rooms["205"]["status"] == "done"
    assert rooms["205"]["serial_last4"] == "8217"


def test_saying_no_asks_for_another_photo(client: TestClient, table: Table) -> None:
    sid = session(client, "205")
    send(client, sid, meter_photo())
    assert confirm(client, sid, "no")["action"] == "retake"
    assert table.get_room("hostel-a", "205").meter_serial is None  # type: ignore[union-attr]
    assert confirm(client, sid)["error"] == "nothing_to_confirm"


def test_meter_linked_to_another_room_is_refused(client: TestClient) -> None:
    first = session(client, "204")
    send(client, first, meter_photo())
    confirm(client, first)

    sid = session(client, "205")
    body = send(client, sid, meter_photo())
    assert body["action"] == "retake"
    assert body["hint"] == "Ye meter Room 204 se juda hai. Room 205 ka meter dhoondho."
    assert send(client, sid, meter_photo())["action"] == "review"


def test_two_rooms_racing_for_one_meter(client: TestClient, table: Table) -> None:
    a, b = session(client, "204"), session(client, "205")
    send(client, a, meter_photo())
    send(client, b, meter_photo())
    assert confirm(client, a)["saved"]["status"] == "baseline"
    assert confirm(client, b)["error"] == "meter_taken"
    assert table.get_room("hostel-a", "205").meter_serial is None  # type: ignore[union-attr]


def test_unreadable_serial_gets_three_tries_then_review(client: TestClient) -> None:
    sid = session(client, "205")
    no_serial = meter_photo(serial="kWh")
    actions = [send(client, sid, no_serial) for _ in range(4)]
    assert [a["action"] for a in actions] == ["retake", "retake", "retake", "review"]
    assert actions[0]["hint"].startswith("Serial number nahi padh paaye")
