from __future__ import annotations

import hashlib
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from app.config import Settings
from app.domain.readings import ReadingRecord, ReadingStatus
from app.domain.rounds import Room, RoomStatus
from app.domain.sessions import Session


class Conflict(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def link_key(token: str) -> dict[str, str]:
    return {"PK": f"LINK#{token_hash(token)}", "SK": "LINK"}


def hostel_pk(hostel_id: str) -> str:
    return f"HOSTEL#{hostel_id}"


def room_key(hostel_id: str, room_id: str) -> dict[str, str]:
    return {"PK": hostel_pk(hostel_id), "SK": f"ROOM#{room_id}"}


def readings_pk(hostel_id: str, room_id: str) -> str:
    return f"HOSTEL#{hostel_id}#ROOM#{room_id}"


def meter_key(serial: str) -> dict[str, str]:
    return {"PK": f"METER#{serial}", "SK": "METER"}


def _strip(item: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in item.items() if k not in ("PK", "SK")}


class Table:
    def __init__(self, settings: Settings) -> None:
        resource = boto3.resource("dynamodb", **settings.aws_kwargs())  # type: ignore[call-overload]
        self.client = resource.meta.client
        self.name = settings.table_name
        self.table = resource.Table(settings.table_name)

    def create_if_missing(self) -> None:
        try:
            self.client.describe_table(TableName=self.name)
            return
        except ClientError as error:
            if error.response["Error"]["Code"] != "ResourceNotFoundException":
                raise
        self.client.create_table(
            TableName=self.name,
            KeySchema=[
                {"AttributeName": "PK", "KeyType": "HASH"},
                {"AttributeName": "SK", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "PK", "AttributeType": "S"},
                {"AttributeName": "SK", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        self.client.get_waiter("table_exists").wait(TableName=self.name)
        self.client.update_time_to_live(
            TableName=self.name,
            TimeToLiveSpecification={"Enabled": True, "AttributeName": "expires_at"},
        )

    def put_link(self, token: str, hostel_id: str, caretaker: str) -> None:
        self.table.put_item(
            Item={**link_key(token), "hostel_id": hostel_id, "caretaker": caretaker}
        )

    def get_link(self, token: str) -> dict[str, Any] | None:
        item = self.table.get_item(Key=link_key(token)).get("Item")
        return _strip(item) if item else None

    def put_hostel(self, hostel_id: str, name: str) -> None:
        self.table.put_item(Item={"PK": hostel_pk(hostel_id), "SK": "META", "name": name})

    def get_hostel_name(self, hostel_id: str) -> str | None:
        item = self.table.get_item(Key={"PK": hostel_pk(hostel_id), "SK": "META"}).get("Item")
        return str(item["name"]) if item else None

    def put_room(self, room: Room) -> None:
        self.table.put_item(
            Item={**room_key(room.hostel_id, room.room_id), **room.model_dump(exclude_none=True)}
        )

    def get_room(self, hostel_id: str, room_id: str) -> Room | None:
        item = self.table.get_item(Key=room_key(hostel_id, room_id)).get("Item")
        return Room.model_validate(_strip(item)) if item else None

    def put_session(self, session: Session) -> None:
        self.table.put_item(
            Item={
                "PK": f"SESSION#{session.session_id}",
                "SK": "SESSION",
                "data": session.model_dump_json(),
                "expires_at": session.expires_at,
            }
        )

    def get_session(self, session_id: str, now: int) -> Session | None:
        item = self.table.get_item(Key={"PK": f"SESSION#{session_id}", "SK": "SESSION"}).get("Item")
        if not item:
            return None
        session = Session.model_validate_json(str(item["data"]))
        return None if session.expired(now) else session

    def list_rooms(self, hostel_id: str) -> list[Room]:
        response = self.table.query(
            KeyConditionExpression=Key("PK").eq(hostel_pk(hostel_id))
            & Key("SK").begins_with("ROOM#")
        )
        rooms = [Room.model_validate(_strip(i)) for i in response["Items"]]
        return sorted(rooms, key=lambda r: (len(r.room_id), r.room_id))

    def meter_owner(self, serial: str) -> str | None:
        item = self.table.get_item(Key=meter_key(serial)).get("Item")
        return str(item["room_id"]) if item else None

    def commit_reading(self, record: ReadingRecord, link_serial: str | None = None) -> None:
        """Write the reading and the room's new state together, or neither."""
        state = {
            "round": record.round_id,
            "status": RoomStatus.REVIEW.value
            if record.status == ReadingStatus.NEEDS_REVIEW
            else RoomStatus.DONE.value,
            "note": record.reason
            if record.status == ReadingStatus.NEEDS_REVIEW
            else record.status.value,
        }
        sets = ["round_state = :state"]
        values: dict[str, Any] = {
            ":state": state,
            ":round": record.round_id,
            ":done": RoomStatus.DONE.value,
        }
        if record.counts_as_reading:
            sets += ["previous_reading = :reading", "previous_at = :at"]
            values |= {":reading": record.reading, ":at": record.recorded_at[:10]}
        condition = (
            "(attribute_not_exists(round_state) OR round_state.#r <> :round "
            "OR round_state.#s <> :done)"
        )
        actions: list[dict[str, Any]] = [
            {
                "Put": {
                    "TableName": self.name,
                    "Item": (
                        {
                            "PK": readings_pk(record.hostel_id, record.room_id),
                            "SK": f"READ#{record.recorded_at}",
                            "status": record.status.value,
                            "data": record.model_dump_json(),
                        }
                    ),
                }
            }
        ]
        if link_serial:
            sets.append("meter_serial = :serial")
            values[":serial"] = link_serial
            condition += " AND attribute_not_exists(meter_serial)"
            actions.append(
                {
                    "Put": {
                        "TableName": self.name,
                        "Item": (
                            {
                                **meter_key(link_serial),
                                "hostel_id": record.hostel_id,
                                "room_id": record.room_id,
                            }
                        ),
                        "ConditionExpression": "attribute_not_exists(PK)",
                    }
                }
            )
        actions.append(
            {
                "Update": {
                    "TableName": self.name,
                    "Key": (room_key(record.hostel_id, record.room_id)),
                    "UpdateExpression": "SET " + ", ".join(sets),
                    "ConditionExpression": "attribute_exists(PK) AND " + condition,
                    "ExpressionAttributeNames": {"#r": "round", "#s": "status"},
                    "ExpressionAttributeValues": (values),
                }
            }
        )
        try:
            self.client.transact_write_items(TransactItems=actions)
        except ClientError as error:
            if error.response["Error"]["Code"] != "TransactionCanceledException":
                raise
            reasons = [r.get("Code") for r in error.response.get("CancellationReasons", [])]
            if link_serial and len(reasons) > 1 and reasons[1] == "ConditionalCheckFailed":
                raise Conflict("meter_taken") from error
            raise Conflict("room_changed") from error

    def latest_reading(self, hostel_id: str, room_id: str, round_id: str) -> ReadingRecord | None:
        response = self.table.query(
            KeyConditionExpression=Key("PK").eq(readings_pk(hostel_id, room_id))
            & Key("SK").begins_with("READ#"),
            ScanIndexForward=False,
            Limit=20,
        )
        for item in response["Items"]:
            record = ReadingRecord.model_validate_json(str(item["data"]))
            if record.round_id == round_id and record.counts_as_reading:
                return record
        return None
