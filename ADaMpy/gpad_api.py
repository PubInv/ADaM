"""Tiny GPAD_API alarm protocol helpers.

GPAD_API alarm wire format:
    a<lvl><description>

- 'a' is the message type for an alarm.
- <lvl> is a single digit severity level (0-9, typically 0-5).
- <description> is up to `width` characters (default 80). Anything longer is truncated.
- Implementations often treat the description field as fixed width (80 chars), so we
  optionally pad with spaces on encode.

Example:
    a5My hair is on fire.

This module is intentionally tiny so it can be copied/used across scripts.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GpadAlarm:
    severity: int
    description: str


def encode_gpad_alarm(severity: int, description: str, width: int = 80, pad: bool = True) -> str:
    sev = int(severity) if severity is not None else 0
    if sev < 0:
        sev = 0
    if sev > 9:
        sev = 9

    body = (description or "")
    body = body.replace("\r", " ").replace("\n", " ")
    body = body[:width]

    if pad:
        body = body.ljust(width, " ")

    return f"a{sev}{body}"


def decode_gpad_alarm(payload: str, width: int = 80) -> GpadAlarm:
    s = (payload or "").strip("\r\n")
    if len(s) < 2 or s[0] != "a":
        raise ValueError("not a GPAD alarm")

    try:
        sev = int(s[1])
    except ValueError as e:
        raise ValueError("invalid severity digit") from e

    desc = s[2 : 2 + width]
    return GpadAlarm(severity=sev, description=desc.rstrip(" "))


# Optional tiny ACK helpers in the same "tiny library"
# Preferred ACK format for this project:
#   k|<annunciator>|<status>|<alarm_id>|<ack_at>

ACK_PREFIX = "k"


@dataclass(frozen=True)
class GpadAck:
    annunciator: str
    status: str
    alarm_id: str
    ack_at: str


def encode_gpad_ack(annunciator: str, status: str, alarm_id: str = "", ack_at: str = "") -> str:
    def _safe(x: str) -> str:
        return (x or "").replace("|", "/")

    return "|".join([ACK_PREFIX, _safe(annunciator), _safe(status), _safe(alarm_id), _safe(ack_at)])


def decode_gpad_ack(payload: str) -> GpadAck:
    s = (payload or "").strip("\r\n")
    if not s.startswith("k|"):
        raise ValueError("not a GPAD ack")

    parts = s.split("|")
    while len(parts) < 5:
        parts.append("")
    _, ann, status, alarm_id, ack_at = parts[:5]
    return GpadAck(annunciator=ann, status=status, alarm_id=alarm_id, ack_at=ack_at)
