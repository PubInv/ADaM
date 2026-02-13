"""GPAP (General Purpose Alarm Protocol) helpers.

This project previously used a GPAD-like fixed-width alarm format and a custom ACK
format. For this week's tasks we switch to GPAP as defined here:
https://github.com/PubInv/gpap

GPAP Alarm message:
  a<sev>{<msg_id>}<text>
  - <sev> is 0-5 (single digit)
  - {<msg_id>} is optional, hex recommended
  - <text> is up to 80 chars (microcontroller-friendly)

GPAP Operator response:
  o<action>{<msg_id>}
  - action is one of: a (ack), c (complete), d (dismiss), s (shelve)
  - {<msg_id>} is optional. If omitted, receiver may apply to "current" alarm.

Project-specific extension (not in GPAP):
  m  -> mute
  u  -> unmute
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Optional


# ---------------- GPAP Alarm ----------------

_ALARM_RE = re.compile(r"^a(?P<sev>[0-9])(?:(?P<id>\{[0-9A-Fa-f]+\}))?(?P<text>.*)$")
_RESP_RE = re.compile(r"^o(?P<action>[acds])(?:(?P<id>\{[0-9A-Fa-f]+\}))?$")


@dataclass(frozen=True)
class GpapAlarm:
    severity: int
    text: str
    msg_id: Optional[str] = None  # hex string without braces


def _clamp_sev(sev: int) -> int:
    try:
        sev_i = int(sev)
    except Exception:
        sev_i = 0
    if sev_i < 0:
        sev_i = 0
    if sev_i > 5:
        sev_i = 5
    return sev_i


def encode_gpap_alarm(severity: int, text: str, msg_id: str | None = None, max_len: int = 80) -> str:
    """Encode an alarm payload in GPAP format."""
    sev = _clamp_sev(severity)
    clean = (text or "").replace("\r", " ").replace("\n", " ")

    if msg_id:
        mid = re.sub(r"[^0-9A-Fa-f]", "", str(msg_id)).upper()
        if not mid:
            mid = None
    else:
        mid = None

    prefix = f"a{sev}" + (f"{{{mid}}}" if mid else "")
    room = max_len - len(prefix)
    if room < 0:
        room = 0
    clean = clean[:room]
    return prefix + clean


def decode_gpap_alarm(payload: str) -> GpapAlarm:
    s = (payload or "").strip("\r\n")
    m = _ALARM_RE.match(s)
    if not m:
        raise ValueError("not a GPAP alarm")
    sev = _clamp_sev(int(m.group("sev")))
    mid = m.group("id")
    if mid:
        mid = mid.strip("{}").upper()
    text = (m.group("text") or "").strip()
    return GpapAlarm(severity=sev, text=text, msg_id=mid)


# ---------------- GPAP Operator Response ----------------

@dataclass(frozen=True)
class GpapResponse:
    action: str  # a/c/d/s
    msg_id: Optional[str] = None  # hex without braces


def encode_gpap_response(action: str, msg_id: str | None = None) -> str:
    a = (action or "").strip().lower()
    if a not in ("a", "c", "d", "s"):
        raise ValueError("action must be one of a/c/d/s")
    if msg_id:
        mid = re.sub(r"[^0-9A-Fa-f]", "", str(msg_id)).upper()
        if mid:
            return f"o{a}{{{mid}}}"
    return f"o{a}"


def decode_gpap_response(payload: str) -> GpapResponse:
    s = (payload or "").strip("\r\n").strip()
    m = _RESP_RE.match(s)
    if not m:
        raise ValueError("not a GPAP response")
    action = m.group("action").lower()
    mid = m.group("id")
    if mid:
        mid = mid.strip("{}").upper()
    return GpapResponse(action=action, msg_id=mid)


# ---------------- Backward-compatible aliases ----------------
# Your older scripts import these names. Keep them so nothing explodes.

@dataclass(frozen=True)
class GpadAlarm:
    severity: int
    description: str


def encode_gpad_alarm(severity: int, description: str, width: int = 80, pad: bool = False) -> str:
    return encode_gpap_alarm(severity, description, msg_id=None, max_len=80)


def decode_gpad_alarm(payload: str, width: int = 80) -> GpadAlarm:
    a = decode_gpap_alarm(payload)
    return GpadAlarm(severity=a.severity, description=a.text)


# Legacy ACK helpers kept for compatibility only.
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
        raise ValueError("not a legacy k| ack")
    parts = s.split("|")
    while len(parts) < 5:
        parts.append("")
    _, ann, status, alarm_id, ack_at = parts[:5]
    return GpadAck(annunciator=ann, status=status, alarm_id=alarm_id, ack_at=ack_at)