from __future__ import annotations

import json
import time
import uuid
from datetime import datetime
from typing import Annotated, Any, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, File, Form, Request, UploadFile
from pydantic import BaseModel

from app.agent.loop import Agent, AgentRun
from app.agent.policy import Action, Decision
from app.agent.providers import build_decider
from app.agent.summary import summarize
from app.api.deps import RoundContext, RoundDep, SettingsDep, TableDep
from app.api.errors import UNKNOWN_ROOM, ApiError
from app.domain.factors import UNIT_LABELS, co2_kg
from app.domain.readings import ReadingRecord, ReadingStatus
from app.domain.rounds import Room, RoomStatus, status_for
from app.domain.sessions import Mode, Session
from app.domain.units import consumption, went_backwards
from app.store.photos import PhotoStore
from app.store.table import Conflict, Table
from app.vision.client import build_vision
from app.vision.geometry import split_quad
from app.vision.pipeline import DIGIT_CONFIDENCE_THRESHOLD, decode_image
from app.vision.serials import last4, normalize

router = APIRouter(prefix="/api")

SESSION_GONE = ApiError(404, "session_expired", "Session purana ho gaya, room dobara kholo.")
NOT_A_PHOTO = ApiError(422, "not_a_photo", "Photo padh nahi paaye, dobara lo.")
TOO_LARGE = ApiError(413, "photo_too_large", "Photo bahut badi hai, dobara lo.")
ROOM_DONE = ApiError(409, "room_done", "Is room ki reading is mahine ho chuki hai.")
NOTHING_TO_CONFIRM = ApiError(409, "nothing_to_confirm", "Pehle meter ki photo lo.")
METER_TAKEN = ApiError(409, "meter_taken", "Ye meter kisi aur room se jud chuka hai.")
ROOM_HAS_METER = ApiError(409, "room_has_meter", "Is room ka meter pehle hi juda hai.")
BACKWARDS_REASON = "Reading pichhli se kam hai."


class SessionCreated(BaseModel):
    session_id: str
    mode: Mode


def get_agent(request: Request) -> Agent:
    agent: Agent | None = getattr(request.app.state, "agent", None)
    if agent is None:
        settings = request.app.state.settings
        agent = Agent(
            build_vision(settings.models_dir, settings.vision_url), build_decider(settings)
        )
        request.app.state.agent = agent
    return agent


def _photos(request: Request) -> PhotoStore:
    store: PhotoStore = request.app.state.photos
    return store


def _session(table: TableDep, ctx: RoundContext, session_id: str) -> Session:
    session = table.get_session(session_id, int(time.time()))
    if session is None or session.hostel_id != ctx.hostel_id or session.closed:
        raise SESSION_GONE
    return session


@router.post("/rooms/{room_id}/sessions")
def start_session(
    room_id: str, ctx: RoundDep, table: TableDep, settings: SettingsDep
) -> SessionCreated:
    room = table.get_room(ctx.hostel_id, room_id)
    if room is None:
        raise UNKNOWN_ROOM
    if status_for(room, ctx.round_id) == RoomStatus.DONE:
        raise ROOM_DONE
    session = Session(
        session_id=uuid.uuid4().hex,
        hostel_id=ctx.hostel_id,
        room_id=room_id,
        round_id=ctx.round_id,
        mode=Mode.READING if room.meter_serial else Mode.ADD_METER,
        expires_at=int(time.time()) + settings.session_ttl_hours * 3600,
    )
    table.put_session(session)
    return SessionCreated(session_id=session.session_id, mode=session.mode)


def _view(run: AgentRun) -> dict[str, Any]:
    analysis, decision = run.analysis, run.decision
    display = analysis.display
    marks = [{"kind": "glare", "box": list(b)} for b in analysis.quality.glare_boxes]
    return {
        "action": decision.action.value,
        "hint": decision.hint,
        "reason": decision.reason,
        "decided_by": decision.decided_by,
        "image": {"width": analysis.width, "height": analysis.height},
        "marks": marks,
        "display": {
            "text": display.text,
            "confidences": display.confidences,
            "digit_quads": split_quad(display.quad, len(display.text)) if display.text else [],
            "unclear_positions": display.unclear_positions,
            "threshold": DIGIT_CONFIDENCE_THRESHOLD,
        }
        if display
        else None,
        "serial": {
            "text": analysis.serial.text.upper(),
            "quad": analysis.serial.quad,
            "status": analysis.serial_status,
        }
        if analysis.serial
        else None,
        "reading": display.text if display and decision.action == Action.SAVE else None,
        "steps": run.steps,
    }


@router.post("/sessions/{session_id}/photos")
def submit_photo(
    session_id: str,
    request: Request,
    ctx: RoundDep,
    table: TableDep,
    settings: SettingsDep,
    photo: Annotated[UploadFile, File()],
    client_photo_id: Annotated[str, Form(min_length=8, max_length=64)],
    location: Annotated[str, Form()] = "{}",
) -> dict[str, Any]:
    session = _session(table, ctx, session_id)
    if client_photo_id in session.responses:
        return session.responses[client_photo_id]

    data = photo.file.read(settings.max_photo_bytes + 1)
    if len(data) > settings.max_photo_bytes:
        raise TOO_LARGE
    image = decode_image(data)
    if image is None:
        raise NOT_A_PHOTO

    room = table.get_room(ctx.hostel_id, session.room_id)
    if room is None:
        raise UNKNOWN_ROOM

    index = len(session.photo_keys) + 1
    key = f"hostel/{ctx.hostel_id}/{session.round_id}/{session.room_id}/{session_id}/{index}.jpg"
    place = _location(location)
    _photos(request).put(
        key,
        data,
        {
            "server-time": str(int(time.time())),
            "session-id": session_id,
            "client-photo-id": client_photo_id,
            "location": place,
        },
    )
    session.photo_keys.append(key)

    def owner_elsewhere(serial_text: str) -> str | None:
        owner = table.meter_owner(normalize(serial_text))
        return owner if owner and owner != session.room_id else None

    run = get_agent(request).run(image, session, room.meter_serial, owner_elsewhere)
    _guard_backwards(run, room)
    session.trace.extend({"photo": index, **s} for s in run.steps)

    view = _view(run)
    view["photo"] = {
        "index": index,
        "location": place,
        "resolution": f"{image.shape[1]}x{image.shape[0]}",
    }
    view |= _finish(table, session, room, run, place, settings.timezone)
    view["summary"] = summarize(session.trace)
    session.responses[client_photo_id] = view
    table.put_session(session)
    return view


@router.get("/rooms/{room_id}/latest")
def latest(room_id: str, ctx: RoundDep, table: TableDep) -> dict[str, Any]:
    record = table.latest_reading(ctx.hostel_id, room_id, ctx.round_id)
    if record is None:
        raise ApiError(404, "no_reading", "Is mahine ki reading abhi nahi hui.")
    return {"saved": _saved_view(record), "summary": summarize(record.trace)}


def _guard_backwards(run: AgentRun, room: Room) -> None:
    display = run.analysis.display
    if run.decision.action != Action.SAVE or display is None:
        return
    if went_backwards(room.previous_reading, display.text):
        run.decision = Decision(Action.REVIEW, BACKWARDS_REASON, "backwards")
        run.steps.append(
            {
                "step": "decide",
                "action": "review",
                "decided_by": "rule",
                "reason": "backwards",
                "hint": BACKWARDS_REASON,
                "ms": 0.0,
            }
        )


def _record(
    session: Session, room: Room, status: ReadingStatus, place: str, tz: str, **fields: Any
) -> ReadingRecord:
    return ReadingRecord(
        hostel_id=session.hostel_id,
        room_id=session.room_id,
        round_id=session.round_id,
        recorded_at=datetime.now(ZoneInfo(tz)).isoformat(timespec="milliseconds"),
        status=status,
        meter_type=room.meter_type,
        session_id=session.session_id,
        photo_keys=list(session.photo_keys),
        trace=list(session.trace),
        location=place,
        **fields,
    )


def _saved_view(record: ReadingRecord) -> dict[str, Any]:
    return {
        "status": record.status.value,
        "reading": record.reading,
        "units": record.units,
        "unit_label": record.unit_label,
        "co2_kg": record.co2_kg,
        "recorded_at": record.recorded_at,
    }


def _finish(
    table: Table, session: Session, room: Room, run: AgentRun, place: str, tz: str
) -> dict[str, Any]:
    action = run.decision.action
    display = run.analysis.display
    if action == Action.CONFIRM and display is not None and run.analysis.serial is not None:
        serial = normalize(run.analysis.serial.text)
        session.pending_meter = {"serial": serial, "reading": display.text}
        return {
            "confirm": {"serial": serial, "serial_last4": last4(serial), "reading": display.text}
        }
    if action == Action.SAVE and display is not None:
        units = consumption(room.previous_reading, display.text)
        record = _record(
            session,
            room,
            ReadingStatus.SAVED,
            place,
            tz,
            reading=display.text,
            serial=room.meter_serial,
            units=units,
            unit_label=UNIT_LABELS.get(room.meter_type),
            co2_kg=co2_kg(room.meter_type, units),
        )
    elif action == Action.REVIEW:
        record = _record(
            session,
            room,
            ReadingStatus.NEEDS_REVIEW,
            place,
            tz,
            reason=run.decision.hint,
            reading=display.text if display else None,
        )
    else:
        return {}
    try:
        table.commit_reading(record)
    except Conflict as conflict:
        raise ROOM_DONE from conflict
    session.closed = True
    return {"saved": _saved_view(record)} if record.counts_as_reading else {}


def _location(raw: str) -> str:
    try:
        data = json.loads(raw)
        lat, lon = float(data["lat"]), float(data["lon"])
        return f"{lat:.6f},{lon:.6f},{float(data.get('accuracy', 0)):.0f}"
    except (ValueError, KeyError, TypeError):
        return "nahi mili"


class ConfirmAnswer(BaseModel):
    answer: Literal["yes", "no"]


@router.post("/sessions/{session_id}/confirm")
def confirm_meter(
    session_id: str, body: ConfirmAnswer, ctx: RoundDep, table: TableDep, settings: SettingsDep
) -> dict[str, Any]:
    session = _session(table, ctx, session_id)
    pending = session.pending_meter
    if session.mode != Mode.ADD_METER or not pending:
        raise NOTHING_TO_CONFIRM
    room = table.get_room(ctx.hostel_id, session.room_id)
    if room is None:
        raise UNKNOWN_ROOM

    session.pending_meter = None
    if body.answer == "no":
        session.trace.append(
            {
                "step": "decide",
                "action": "retake",
                "reason": "caretaker_said_no",
                "decided_by": "human",
                "hint": "Sahi meter ki photo lo.",
                "ms": 0.0,
            }
        )
        table.put_session(session)
        return {"action": "retake", "hint": "Theek hai, sahi meter ki photo lo."}

    session.trace.append(
        {
            "step": "decide",
            "action": "linked",
            "reason": "caretaker_confirmed",
            "decided_by": "human",
            "hint": "Meter joda",
            "ms": 0.0,
        }
    )
    record = _record(
        session,
        room,
        ReadingStatus.BASELINE,
        "",
        settings.timezone,
        reading=pending["reading"],
        serial=pending["serial"],
        unit_label=UNIT_LABELS.get(room.meter_type),
    )
    try:
        table.commit_reading(record, link_serial=pending["serial"])
    except Conflict as conflict:
        table.put_session(session)
        raise (METER_TAKEN if conflict.reason == "meter_taken" else ROOM_HAS_METER) from conflict
    session.closed = True
    table.put_session(session)
    return {"action": "linked", "saved": _saved_view(record), "summary": summarize(session.trace)}
