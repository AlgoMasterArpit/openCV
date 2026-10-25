from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.domain.rounds import Room
from app.store.table import Table
from tests.api.test_photos import jpeg, meter, send, session
from tests.vision import synth

pytestmark = pytest.mark.usefixtures("models_ready")


def room_205(table: Table, previous: str = "01890") -> None:
    table.put_room(
        Room(
            hostel_id="hostel-a",
            room_id="205",
            meter_serial="48217",
            previous_reading=previous,
            previous_at="2026-10-26",
        )
    )


def statuses(client: TestClient) -> dict[str, str]:
    return {r["room_id"]: r["status"] for r in client.get("/api/round").json()["rooms"]}


def test_saved_reading_has_units_co2_and_summary(client: TestClient, table: Table) -> None:
    room_205(table)
    body = send(client, session(client), jpeg(meter(reading="01910")))
    assert body["saved"]["units"] == 20
    assert body["saved"]["unit_label"] == "kWh"
    assert body["saved"]["co2_kg"] == pytest.approx(14.54)
    assert body["summary"][-1] == {"label": "Reading save", "decided_by": "rule"}

    assert statuses(client)["205"] == "done"
    room = table.get_room("hostel-a", "205")
    assert room is not None
    assert room.previous_reading == "01910"


def test_done_room_shows_saved_card_and_refuses_new_session(
    client: TestClient, table: Table
) -> None:
    room_205(table)
    send(client, session(client), jpeg(meter(reading="01910")))
    assert client.post("/api/rooms/205/sessions").json()["error"] == "room_done"
    latest = client.get("/api/rooms/205/latest").json()
    assert latest["saved"]["reading"] == "01910"
    assert latest["summary"]


def test_closed_session_takes_no_more_photos(client: TestClient, table: Table) -> None:
    room_205(table)
    sid = session(client)
    send(client, sid, jpeg(meter(reading="01910")))
    response = client.post(
        f"/api/sessions/{sid}/photos",
        files={"photo": ("p.jpg", jpeg(meter()), "image/jpeg")},
        data={"client_photo_id": "photo-after-save"},
    )
    assert response.json()["error"] == "session_expired"


def test_backwards_reading_goes_to_review(client: TestClient, table: Table) -> None:
    room_205(table, previous="01950")
    body = send(client, session(client), jpeg(meter(reading="01910")))
    assert body["action"] == "review"
    assert body["hint"] == "Reading pichhli se kam hai."
    assert "saved" not in body
    assert statuses(client)["205"] == "review"
    room = table.get_room("hostel-a", "205")
    assert room is not None
    assert room.previous_reading == "01950"


def test_review_room_can_be_reopened_with_fresh_limits(client: TestClient, table: Table) -> None:
    room_205(table)
    sid = session(client)
    blurry = jpeg(synth.blurred(meter()))
    for _ in range(4):
        last = send(client, sid, blurry)
    assert last["action"] == "review"
    assert last["summary"][-1]["label"] == "Review mein bheja"
    assert statuses(client)["205"] == "review"

    again = session(client)
    assert send(client, again, blurry)["action"] == "retake"
    assert send(client, again, jpeg(meter(reading="01910")))["action"] == "save"
    assert statuses(client)["205"] == "done"
