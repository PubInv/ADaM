from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass


# Version 1 contract:
#   TYPE:<ALARM_TYPE_KEY>|<optional text>
_TYPE_RE = re.compile(r"^\s*TYPE:(?P<key>[A-Za-z0-9_-]+)\|(?P<rest>.*)$")


def normalize_alarm_type_key(value: str | None) -> str | None:
    if value is None:
        return None
    key = str(value).strip().upper().replace("-", "_").replace(" ", "_")
    return key or None


def extract_alarm_type_key(text: str | None) -> str | None:
    raw = (text or "").strip()
    if not raw:
        return None
    m = _TYPE_RE.match(raw)
    if not m:
        return None
    return normalize_alarm_type_key(m.group("key"))


def strip_alarm_type_marker(text: str | None) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    m = _TYPE_RE.match(raw)
    if not m:
        return raw
    return (m.group("rest") or "").strip()


@dataclass(frozen=True)
class AlarmTypeDefinition:
    alarm_type: str
    alarm_number: str
    default_text: str


class AlarmDatabase:
    def __init__(
        self,
        alarm_types: dict[str, AlarmTypeDefinition],
        source_path: str,
        unknown_alarm_number: str = "000",
        unknown_default_text: str = "Unknown alarm type",
    ):
        self.alarm_types = alarm_types
        self.source_path = source_path
        self.unknown_alarm_number = str(unknown_alarm_number or "000").strip() or "000"
        self.unknown_default_text = (
            str(unknown_default_text or "Unknown alarm type").strip() or "Unknown alarm type"
        )

    def get(self, alarm_type: str | None) -> AlarmTypeDefinition | None:
        key = normalize_alarm_type_key(alarm_type)
        if not key:
            return None
        return self.alarm_types.get(key)


def load_alarm_database(path: str) -> AlarmDatabase:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Alarm type database not found: {path}")

    with open(path, "r", encoding="utf-8-sig") as f:
        data = json.load(f)

    raw_types = data.get("alarm_types")
    if not isinstance(raw_types, dict) or not raw_types:
        raise ValueError("alarm_types.json must contain a non-empty object at key 'alarm_types'.")

    unknown_alarm_number = data.get("unknown_alarm_number", "000")
    unknown_default_text = data.get("unknown_default_text", "Unknown alarm type")

    alarm_types: dict[str, AlarmTypeDefinition] = {}
    used_numbers: dict[str, str] = {}

    for raw_key, raw_def in raw_types.items():
        if not isinstance(raw_def, dict):
            raise ValueError(f"alarm_types[{raw_key!r}] must be an object.")

        alarm_type = normalize_alarm_type_key(str(raw_key))
        if not alarm_type:
            raise ValueError(f"Invalid alarm type key: {raw_key!r}")

        alarm_number = str(raw_def.get("alarm_number", "")).strip()
        default_text = str(raw_def.get("default_text", "")).strip()

        if not alarm_number:
            raise ValueError(f"alarm_type={alarm_type} missing required field alarm_number.")
        if not default_text:
            raise ValueError(f"alarm_type={alarm_type} missing required field default_text.")

        if alarm_number in used_numbers:
            other = used_numbers[alarm_number]
            raise ValueError(f"Duplicate alarm_number={alarm_number} for {alarm_type} and {other}.")
        used_numbers[alarm_number] = alarm_type

        alarm_types[alarm_type] = AlarmTypeDefinition(
            alarm_type=alarm_type,
            alarm_number=alarm_number,
            default_text=default_text,
        )

    return AlarmDatabase(
        alarm_types=alarm_types,
        source_path=os.path.abspath(path),
        unknown_alarm_number=unknown_alarm_number,
        unknown_default_text=unknown_default_text,
    )