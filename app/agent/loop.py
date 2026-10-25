from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import Any, Protocol

from app.agent import policy
from app.agent.policy import Action, Decision, Observation, Problem
from app.domain.sessions import Mode, Session
from app.vision.client import Vision
from app.vision.geometry import Image
from app.vision.pipeline import Analysis
from app.vision.serials import last4

log = logging.getLogger("metermind.agent")


class Decider(Protocol):
    def decide(self, obs: Observation) -> Decision: ...


class RuleDecider:
    def decide(self, obs: Observation) -> Decision:
        return policy.decide(obs)


@dataclass
class AgentRun:
    analysis: Analysis
    decision: Decision
    steps: list[dict[str, Any]] = field(default_factory=list)


def observe(
    analysis: Analysis,
    session: Session,
    expected_serial: str | None,
    rereads: list[str],
    linked_room: str | None = None,
) -> Observation:
    display = analysis.display
    return Observation(
        mode=session.mode,
        room_id=session.room_id,
        quality_issues=list(analysis.quality.issues),
        glare_cells=list(analysis.quality.glare_cells),
        serial_status=analysis.serial_status,
        serial_text=analysis.serial.text if analysis.serial else None,
        expected_last4=last4(expected_serial) if expected_serial else None,
        display_text=display.text if display else None,
        display_confidences=list(display.confidences) if display else [],
        unclear_positions=display.unclear_positions if display else [],
        rereads_done=list(rereads),
        counters=session.counters.model_copy(),
        linked_room=linked_room,
    )


def _step(name: str, started: float, **details: Any) -> dict[str, Any]:
    return {"step": name, "ms": round((time.perf_counter() - started) * 1000, 1), **details}


def _decision_step(decision: Decision, started: float) -> dict[str, Any]:
    return _step(
        "decide",
        started,
        action=decision.action.value,
        decided_by=decision.decided_by,
        reason=decision.reason,
        hint=decision.hint,
        **({"variant": decision.variant} if decision.variant else {}),
        **({"notes": decision.notes} if decision.notes else {}),
    )


class Agent:
    def __init__(self, vision: Vision, decider: Decider) -> None:
        self.vision = vision
        self.decider = decider

    def run(
        self,
        image: Image,
        session: Session,
        expected_serial: str | None,
        linked_room_for: Callable[[str], str | None] | None = None,
    ) -> AgentRun:
        started = time.perf_counter()
        analysis = self.vision.analyze(image, expected_serial)
        steps = [
            _step(
                "perceive",
                started,
                quality=analysis.quality.issues,
                glare_cells=analysis.quality.glare_cells,
                serial_status=analysis.serial_status,
                display=analysis.display.text if analysis.display else None,
                confidences=analysis.display.confidences if analysis.display else [],
            )
        ]

        linked_room = None
        if session.mode == Mode.ADD_METER and analysis.serial and linked_room_for:
            linked_room = linked_room_for(analysis.serial.text)

        rereads: list[str] = []
        while True:
            obs = observe(analysis, session, expected_serial, rereads, linked_room)
            started = time.perf_counter()
            decision = self.decider.decide(obs)
            if decision.action not in policy.allowed_actions(obs):
                fallback = policy.decide(obs)
                decision = replace(
                    fallback, notes=[f"rejected {decision.action.value} from {decision.decided_by}"]
                )
            steps.append(_decision_step(decision, started))
            if decision.action != Action.REREAD or analysis.display is None or rereads:
                break
            started = time.perf_counter()
            variant = decision.variant or policy.next_variant(obs) or "clahe"
            display = self.vision.reread(image, analysis.display, variant)
            rereads.append(variant)
            analysis = replace(analysis, display=display)
            steps.append(
                _step(
                    "reread",
                    started,
                    variant=variant,
                    display=display.text,
                    confidences=display.confidences,
                )
            )

        _count(session, analysis, decision)
        log.info(
            "agent decision",
            extra={
                "session_id": session.session_id,
                "action": decision.action.value,
                "decided_by": decision.decided_by,
            },
        )
        return AgentRun(analysis, decision, steps)


def _count(session: Session, analysis: Analysis, decision: Decision) -> None:
    counters = session.counters
    if analysis.serial_status == "match":
        counters.mismatch = 0
    if decision.problem and decision.action in (Action.RETAKE, Action.NEW_PHOTO):
        key = Problem(decision.problem).value
        setattr(counters, key, getattr(counters, key) + 1)
