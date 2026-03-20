from __future__ import annotations

from flask import Flask, render_template, request, jsonify, redirect, url_for
from pathlib import Path
from datetime import datetime
import json
import time
import threading
import uuid
import re

import paho.mqtt.client as mqtt

from ADaMpy.gpad_api import (
    encode_gpap_alarm,
    decode_gpap_alarm,
    encode_gpap_response,
)


def new_msg_id() -> str:
    return uuid.uuid4().hex[:5].upper()


app = Flask(__name__)

ADAMPY_DIR = Path(__file__).resolve().parent
LOG_FILE = ADAMPY_DIR / "adam_server.log"
CONFIG_FILE = ADAMPY_DIR / "config" / "adam_config.json"
ALARM_TYPES_FILE = ADAMPY_DIR / "config" / "alarm_types.json"
HARDWARE_KRAKES_FILE = ADAMPY_DIR / "config" / "hardware_krakes.json"

APP_LOCK = threading.Lock()
WEB_KRAKES: dict[str, "WebKrake"] = {}
HARDWARE_KRAKES: list[dict] = []

MQTT_CLIENT = None
MQTT_READY = False
MQTT_SUBSCRIPTIONS: set[str] = set()


def read_last_lines(path: Path, limit: int = 100) -> list[str]:
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        return [line.rstrip("\n") for line in lines[-limit:]]
    except Exception as e:
        return [f"Error reading file: {e}"]


def append_app_log(message: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[WEB {ts}] {message}"
    print(line)
    try:
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def load_cfg() -> dict:
    with open(CONFIG_FILE, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def save_cfg(cfg: dict) -> None:
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def resolve_alarm_db_path(cfg: dict) -> Path:
    configured = str(cfg.get("alarm_db_file", "alarm_types.json")).strip() or "alarm_types.json"
    p = Path(configured)
    if p.is_absolute():
        return p
    return (CONFIG_FILE.parent / p).resolve()


def load_alarm_types_data() -> dict:
    path = ALARM_TYPES_FILE
    if not path.exists():
        return {"alarm_types": {}}
    with open(path, "r", encoding="utf-8-sig") as f:
        data = json.load(f)
    if "alarm_types" not in data or not isinstance(data["alarm_types"], dict):
        data["alarm_types"] = {}
    return data


def save_alarm_types_data(data: dict) -> None:
    with open(ALARM_TYPES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def load_alarm_type_keys() -> list[str]:
    data = load_alarm_types_data()
    keys = [str(k).strip().upper() for k in data.get("alarm_types", {}).keys()]
    keys = [k for k in keys if k]
    keys.sort()
    return keys


def load_hardware_krakes() -> list[dict]:
    if not HARDWARE_KRAKES_FILE.exists():
        return []
    with open(HARDWARE_KRAKES_FILE, "r", encoding="utf-8-sig") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    return data.get("hardware_krakes", [])


def save_hardware_krakes(items: list[dict]) -> None:
    with open(HARDWARE_KRAKES_FILE, "w", encoding="utf-8") as f:
        json.dump({"hardware_krakes": items}, f, indent=2)


class WebKrake:
    def __init__(self, krake_id: str, name: str, annunciator_topic: str, cfg: dict):
        self.krake_id = krake_id
        self.name = name.strip() or krake_id
        self.annunciator_topic = annunciator_topic.strip()
        self.ack_topic_base = cfg.get("ack_topic", "adam/acks")
        self.ack_topic = f"{self.ack_topic_base}/{self.annunciator_topic}"

        self.policy_name = str(cfg.get("policy", "")).strip().upper()
        if self.policy_name == "SEVERITY_PAUSE":
            self.pause_seconds = float(cfg.get("severity_pause_seconds", cfg.get("pause_seconds", 20.0)))
        else:
            self.pause_seconds = 0.0

        self.current_msg_id: str | None = None
        self.current_sev: int | None = None
        self.current_text: str = ""
        self.muted: bool = False
        self.last_event: str = "Created"
        self.last_updated: str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        self.hold_until_ts: float | None = None
        self.buffered_alarm: tuple[str | None, int, str] | None = None
        self._hold_timer: threading.Timer | None = None
        self._lock = threading.Lock()

    def to_dict(self) -> dict:
        remaining_hold = 0.0
        if self.hold_until_ts:
            remaining_hold = max(0.0, self.hold_until_ts - time.time())

        return {
            "krake_id": self.krake_id,
            "name": self.name,
            "annunciator_topic": self.annunciator_topic,
            "ack_topic": self.ack_topic,
            "current_msg_id": self.current_msg_id,
            "current_sev": self.current_sev,
            "current_text": self.current_text,
            "muted": self.muted,
            "last_event": self.last_event,
            "last_updated": self.last_updated,
            "pause_seconds": self.pause_seconds,
            "hold_remaining": round(remaining_hold, 1),
            "buffered_alarm": self.buffered_alarm,
        }

    def _touch(self, event: str) -> None:
        self.last_event = event
        self.last_updated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _cancel_hold_timer(self) -> None:
        if self._hold_timer:
            try:
                self._hold_timer.cancel()
            except Exception:
                pass
            self._hold_timer = None

    def _start_hold_timer(self) -> None:
        self._cancel_hold_timer()
        if self.hold_until_ts is None:
            return

        delay = float(self.hold_until_ts) - time.time()
        if delay <= 0:
            delay = 0.01

        self._hold_timer = threading.Timer(delay, self._on_hold_expired)
        self._hold_timer.daemon = True
        self._hold_timer.start()

    def _begin_hold_now(self) -> None:
        if self.pause_seconds <= 0:
            self.hold_until_ts = None
            self._cancel_hold_timer()
            return
        self.hold_until_ts = time.time() + float(self.pause_seconds)
        self._start_hold_timer()

    def _in_hold(self) -> bool:
        if self.hold_until_ts is None:
            return False
        return time.time() < float(self.hold_until_ts)

    def _on_hold_expired(self) -> None:
        with self._lock:
            now = time.time()
            if self.hold_until_ts is None:
                return
            if now < float(self.hold_until_ts):
                self._start_hold_timer()
                return

            self.hold_until_ts = None

            if self.buffered_alarm is not None:
                mid, sev, text = self.buffered_alarm
                self.buffered_alarm = None
                self._display_alarm(mid, sev, text)
                self._begin_hold_now()
                return

            self._touch("Hold expired")

    def _display_alarm(self, msg_id: str | None, sev: int, text: str) -> None:
        self.current_msg_id = (msg_id or "").upper() if msg_id else None
        self.current_sev = int(sev)
        self.current_text = text or ""
        self._touch(f"Displayed alarm sev={sev}")

    def receive_alarm(self, msg_id: str | None, sev: int, text: str) -> None:
        with self._lock:
            if self.pause_seconds > 0 and self._in_hold():
                self.buffered_alarm = (msg_id, sev, text)
                self._touch(f"Buffered alarm sev={sev}")
                return

            self.buffered_alarm = None
            self._display_alarm(msg_id, sev, text)
            self._begin_hold_now()

    def clear_display_only(self, reason: str) -> None:
        self.current_msg_id = None
        self.current_sev = None
        self.current_text = ""
        self._touch(reason)

    def publish_action(self, payload: str) -> bool:
        global MQTT_CLIENT
        if MQTT_CLIENT is None:
            self._touch("MQTT client unavailable")
            return False

        info = MQTT_CLIENT.publish(self.ack_topic, payload, qos=1)
        ok = info.rc == 0
        if ok:
            self._touch(f"Sent action: {payload}")
            append_app_log(f"[KRAKE {self.krake_id}] published to {self.ack_topic}: {payload}")
        else:
            self._touch(f"Publish failed rc={info.rc}")
        return ok

    def apply_action(self, action: str) -> tuple[bool, str]:
        action = (action or "").strip().lower()

        if action in ("a", "c", "d", "s"):
            if not self.current_msg_id:
                return False, "No active alarm"

            payload = encode_gpap_response(action, self.current_msg_id)
            ok = self.publish_action(payload)
            if not ok:
                return False, "Publish failed"

            if action == "c":
                self.clear_display_only("Completed current alarm")
            elif action == "d":
                self.clear_display_only("Dismissed current alarm")
            elif action == "s":
                self.clear_display_only("Shelved current alarm")
            elif action == "a":
                self._touch("Acknowledged current alarm")
            return True, f"Action {action} sent"

        if action == "m":
            self.muted = True
            ok = self.publish_action("m")
            return ok, "Muted" if ok else "Mute publish failed"

        if action == "u":
            self.muted = False
            ok = self.publish_action("u")
            return ok, "Unmuted" if ok else "Unmute publish failed"

        return False, "Unknown action"


def get_cfg_annunciators(cfg: dict) -> list[str]:
    items = cfg.get("annunciators", [])
    if not isinstance(items, list):
        return []
    cleaned = [str(x).strip() for x in items if str(x).strip()]
    return cleaned


def ensure_mqtt_client() -> None:
    global MQTT_CLIENT, MQTT_READY

    if MQTT_READY and MQTT_CLIENT is not None:
        return

    cfg = load_cfg()
    broker = cfg.get("broker_host", "public.cloud.shiftr.io")
    port = int(cfg.get("broker_port", 1883))
    username = cfg.get("username", "public")
    password = cfg.get("password", "public")

    kwargs = {"client_id": f"ADaMWeb-{uuid.uuid4().hex[:6]}"}
    try:
        kwargs["callback_api_version"] = mqtt.CallbackAPIVersion.VERSION2
    except Exception:
        pass

    client = mqtt.Client(**kwargs)
    if username and password:
        client.username_pw_set(username, password)

    def on_connect(client, userdata, flags, rc, properties=None):
        append_app_log(f"MQTT connected rc={rc}")
        topics = set(get_cfg_annunciators(load_cfg()))
        with APP_LOCK:
            topics.update(k.annunciator_topic for k in WEB_KRAKES.values())

        for topic in sorted(topics):
            client.subscribe(topic, qos=1)
            MQTT_SUBSCRIPTIONS.add(topic)
            append_app_log(f"Subscribed to topic: {topic}")

    def on_message(client, userdata, msg):
        payload = msg.payload.decode("utf-8", errors="replace").strip("\r\n")
        try:
            alarm = decode_gpap_alarm(payload)
        except Exception:
            return

        msg_id = (alarm.msg_id or "").upper() if alarm.msg_id else None
        sev = int(alarm.severity)
        text = alarm.text

        with APP_LOCK:
            for krake in WEB_KRAKES.values():
                if krake.annunciator_topic == msg.topic:
                    krake.receive_alarm(msg_id, sev, text)

    def on_log(client, userdata, paho_log_level, message):
        try:
            if paho_log_level == mqtt.LogLevel.MQTT_LOG_ERR:
                append_app_log(f"MQTT ERROR: {message}")
        except Exception:
            pass

    client.on_connect = on_connect
    client.on_message = on_message
    client.on_log = on_log

    client.connect(broker, port)
    client.loop_start()

    MQTT_CLIENT = client
    MQTT_READY = True


def subscribe_topic_if_needed(topic: str) -> None:
    global MQTT_CLIENT
    topic = (topic or "").strip()
    if not topic:
        return
    ensure_mqtt_client()
    if topic in MQTT_SUBSCRIPTIONS:
        return
    MQTT_CLIENT.subscribe(topic, qos=1)
    MQTT_SUBSCRIPTIONS.add(topic)
    append_app_log(f"Subscribed to topic: {topic}")


def init_state() -> None:
    global HARDWARE_KRAKES
    try:
        HARDWARE_KRAKES[:] = load_hardware_krakes()
    except Exception:
        HARDWARE_KRAKES[:] = []
    ensure_mqtt_client()


def severity_class(sev) -> str:
    try:
        sev = int(sev)
    except Exception:
        return "sev-unknown"
    if sev >= 5:
        return "sev-5"
    if sev == 4:
        return "sev-4"
    if sev == 3:
        return "sev-3"
    if sev == 2:
        return "sev-2"
    if sev == 1:
        return "sev-1"
    return "sev-0"


def parse_log_timestamp(line: str) -> datetime | None:
    web_match = re.match(r"^\[WEB\s+(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\]", line)
    if web_match:
        try:
            return datetime.strptime(web_match.group(1), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None

    std_match = re.match(
        r"^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})(?:,(\d{1,6}))?",
        line
    )
    if std_match:
        base = std_match.group(1)
        fraction = std_match.group(2)
        try:
            if fraction:
                fraction = (fraction + "000000")[:6]
                return datetime.strptime(f"{base},{fraction}", "%Y-%m-%d %H:%M:%S,%f")
            return datetime.strptime(base, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None

    return None


def extract_line_severity(line: str) -> int | None:
    match = re.search(r"\bsev\s*=\s*(\d)\b", line, flags=re.IGNORECASE)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None
    return None


def extract_line_msg_id(line: str) -> str | None:
    patterns = [
        r"\bmsg_id\s*=\s*([A-Za-z0-9\-]+)",
        r"\bid\s*=\s*([A-Za-z0-9\-]+)",
        r"\balarm_id\s*=\s*([A-Za-z0-9_\-:/]+)",
        r"\bto_msg_id\s*=\s*([A-Za-z0-9\-]+)",
        r"\bfrom_msg_id\s*=\s*([A-Za-z0-9\-]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, line, flags=re.IGNORECASE)
        if match:
            value = (match.group(1) or "").strip()
            return value or None
    return None


def classify_log_event(line: str) -> tuple[str, str, int | None, str]:
    upper = line.upper()
    severity = extract_line_severity(line)

    if upper.startswith("[WEB "):
        if "SPAWNED WEB KRAKE" in upper:
            return "krake", "Web Krake Spawned", severity, severity_class(severity)
        if "[KRAKE " in upper:
            return "web_ack", "Web Krake Ack Publish", severity, severity_class(severity)
        if "PUBLISHED TO " in upper:
            return "web_publish", "Web Publish", severity, severity_class(severity)
        if "SUBSCRIBED TO TOPIC" in upper:
            return "web_subscribe", "Web Subscribe", severity, severity_class(severity)
        if "MQTT CONNECTED" in upper:
            return "connect", "Web MQTT Connected", severity, severity_class(severity)
        return "web", "Web Event", severity, severity_class(severity)

    if " ALARM OUTSIDE DATABASE " in upper or upper.startswith("WARNING "):
        sev = severity if severity is not None else 4
        return "warning", "Warning", sev, severity_class(sev)

    if "MQTT ERROR" in upper or " ERROR " in upper:
        sev = severity if severity is not None else 5
        return "error", "Error", sev, severity_class(sev)

    if "OVERRIDE " in upper:
        return "override", "Override", severity, severity_class(severity)

    if "UNSHELVE " in upper:
        return "unshelve", "Unshelve", severity, severity_class(severity)

    if "MUTE_CHANGE" in upper:
        return "mute", "Mute Change", severity, severity_class(severity)

    if "RECEIVE ACK " in upper:
        return "ack", "Ack Received", severity, severity_class(severity)

    if "OP ACTION=" in upper:
        if "STATUS=COMPLETED" in upper:
            return "operator", "Operator Complete", severity, severity_class(severity)
        if "STATUS=ACKNOWLEDGED" in upper:
            return "operator", "Operator Acknowledge", severity, severity_class(severity)
        if "STATUS=SHELVED" in upper:
            return "operator", "Operator Shelve", severity, severity_class(severity)
        if "STATUS=ACTIVE" in upper:
            return "operator", "Operator Active", severity, severity_class(severity)
        return "operator", "Operator Action", severity, severity_class(severity)

    if "RECEIVE ALARM " in upper:
        label = f"Alarm Received Sev {severity}" if severity is not None else "Alarm Received"
        return "alarm_received", label, severity, severity_class(severity)

    if "SEND ALARM " in upper:
        label = f"Alarm Sent Sev {severity}" if severity is not None else "Alarm Sent"
        return "alarm_sent", label, severity, severity_class(severity)

    if "CONNECTED RC=" in upper or "CONNECT RC=" in upper:
        return "connect", "Connected", severity, severity_class(severity)

    if "SUBSCRIBED ALARM_TOPIC" in upper or "ACK TOPIC BASE=" in upper or "ALARM TOPIC=" in upper:
        return "connect", "Subscription Config", severity, severity_class(severity)

    if "OUT TOPICS=" in upper or "ANNUNCIATORS" in upper or "BROKER=" in upper or "POLICY=" in upper or "TICK=" in upper:
        return "config", "Config", severity, severity_class(severity)

    if upper.rstrip().endswith("STOPPED"):
        return "lifecycle", "Stopped", severity, severity_class(severity)

    return "other", "Log", severity, severity_class(severity)


def build_log_events(lines: list[str]) -> list[dict]:
    events = []
    for index, line in enumerate(lines):
        timestamp = parse_log_timestamp(line)
        kind, label, severity, sev_class = classify_log_event(line)
        msg_id = extract_line_msg_id(line)

        events.append({
            "raw": line,
            "kind": kind,
            "severity": severity,
            "severity_class": sev_class,
            "label": label,
            "timestamp": timestamp.strftime("%Y-%m-%d %H:%M:%S") if timestamp else None,
            "timestamp_iso": timestamp.isoformat() if timestamp else None,
            "event_index": index + 1,
            "msg_id": msg_id,
        })
    return events


@app.route("/")
def home():
    cfg = load_cfg()
    recent_logs = read_last_lines(LOG_FILE, 12)
    with APP_LOCK:
        web_krake_count = len(WEB_KRAKES)
        hardware_krake_count = len(HARDWARE_KRAKES)

    return render_template(
        "home.html",
        now=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        log_exists=LOG_FILE.exists(),
        config_exists=CONFIG_FILE.exists(),
        alarm_types_exists=ALARM_TYPES_FILE.exists(),
        recent_logs=recent_logs,
        web_krake_count=web_krake_count,
        hardware_krake_count=hardware_krake_count,
        annunciators=get_cfg_annunciators(cfg),
    )


@app.route("/health")
def health():
    cfg = load_cfg()
    with APP_LOCK:
        web_krakes = [k.to_dict() for k in WEB_KRAKES.values()]

    return jsonify({
        "status": "ok",
        "service": "ADaM Flask UI",
        "time": datetime.now().isoformat(),
        "log_file_exists": LOG_FILE.exists(),
        "config_exists": CONFIG_FILE.exists(),
        "alarm_types_exists": ALARM_TYPES_FILE.exists(),
        "mqtt_ready": MQTT_READY,
        "annunciators": get_cfg_annunciators(cfg),
        "web_krakes": web_krakes,
        "hardware_krake_count": len(HARDWARE_KRAKES),
    })


@app.route("/logs")
def logs():
    lines = read_last_lines(LOG_FILE, 250)
    events = build_log_events(lines)
    timeline_events = [event for event in events if event.get("timestamp_iso")]

    summary = {
        "total": len(events),
        "timestamped": len(timeline_events),
        "received": sum(1 for event in events if event["kind"] == "alarm_received"),
        "sent": sum(1 for event in events if event["kind"] == "alarm_sent"),
        "operator": sum(1 for event in events if event["kind"] == "operator"),
        "acks": sum(1 for event in events if event["kind"] in {"ack", "web_ack"}),
        "warnings": sum(1 for event in events if event["kind"] == "warning"),
        "errors": sum(1 for event in events if event["kind"] == "error"),
        "overrides": sum(1 for event in events if event["kind"] == "override"),
    }

    return render_template(
        "logs.html",
        log_file=str(LOG_FILE),
        logs=lines,
        events=events,
        timeline_events=timeline_events,
        summary=summary,
    )


@app.route("/manual-alarm", methods=["GET", "POST"])
def manual_alarm():
    cfg = load_cfg()
    known_keys = []
    try:
        known_keys = load_alarm_type_keys()
    except Exception:
        known_keys = []

    message = None
    error = None

    if request.method == "POST":
        ensure_mqtt_client()

        alarm_type = (request.form.get("alarm_type") or "").strip().upper()
        detail = (request.form.get("detail") or "").strip()
        topic = (request.form.get("topic") or cfg.get("alarm_topic", "adam/in/alarms")).strip()

        try:
            sev = int((request.form.get("severity") or "0").strip())
        except Exception:
            sev = 0

        mid = new_msg_id()

        if alarm_type:
            text = f"TYPE:{alarm_type}|{detail}" if detail else f"TYPE:{alarm_type}|"
        else:
            text = detail or "Untyped alarm test"

        try:
            payload = encode_gpap_alarm(sev, text, msg_id=mid, max_len=80)
            info = MQTT_CLIENT.publish(topic, payload, qos=1)
            if info.rc == 0:
                message = f"Alarm published to {topic} with msg_id={mid}"
                append_app_log(f"Published to {topic}: {payload}")
            else:
                error = f"Publish failed rc={info.rc}"
        except Exception as e:
            error = f"Failed to publish alarm: {e}"

    return render_template(
        "manual_alarm.html",
        known_keys=known_keys,
        default_topic=cfg.get("alarm_topic", "adam/in/alarms"),
        message=message,
        error=error,
    )


@app.route("/config", methods=["GET", "POST"])
def config_page():
    cfg = load_cfg()
    data = load_alarm_types_data()
    message = None
    error = None

    if request.method == "POST":
        action = (request.form.get("action") or "").strip()

        if action == "save_cfg":
            try:
                cfg["broker_host"] = (request.form.get("broker_host") or "").strip()
                cfg["broker_port"] = int((request.form.get("broker_port") or "1883").strip())
                cfg["username"] = (request.form.get("username") or "").strip()
                cfg["password"] = (request.form.get("password") or "").strip()
                cfg["alarm_topic"] = (request.form.get("alarm_topic") or "adam/in/alarms").strip()
                cfg["ack_topic"] = (request.form.get("ack_topic") or "adam/acks").strip()

                annunciators_raw = (request.form.get("annunciators") or "").strip()
                cfg["annunciators"] = [x.strip() for x in annunciators_raw.splitlines() if x.strip()]

                save_cfg(cfg)
                message = "Configuration saved"
            except Exception as e:
                error = f"Failed to save config: {e}"

        elif action == "save_alarm_type":
            try:
                key = (request.form.get("alarm_key") or "").strip().upper()
                if not key:
                    raise ValueError("Alarm key is required")

                severity = int((request.form.get("alarm_severity") or "0").strip())
                default_text = (request.form.get("alarm_default_text") or "").strip()
                alarm_number = (request.form.get("alarm_number") or "").strip()
                audio_file = (request.form.get("audio_file") or "").strip()

                entry = data.get("alarm_types", {}).get(key, {})
                entry["severity"] = severity
                entry["default_text"] = default_text
                entry["alarm_number"] = alarm_number
                entry["audio_file"] = audio_file

                data.setdefault("alarm_types", {})[key] = entry
                save_alarm_types_data(data)
                data = load_alarm_types_data()
                message = f"Alarm type {key} saved"
            except Exception as e:
                error = f"Failed to save alarm type: {e}"

    alarm_types = data.get("alarm_types", {})
    sorted_alarm_types = sorted(alarm_types.items(), key=lambda x: x[0])

    return render_template(
        "config.html",
        cfg=cfg,
        alarm_types=sorted_alarm_types,
        config_file=str(CONFIG_FILE),
        alarm_types_file=str(ALARM_TYPES_FILE),
        message=message,
        error=error,
    )


@app.route("/krakes", methods=["GET"])
def krakes():
    cfg = load_cfg()
    annunciators = get_cfg_annunciators(cfg)
    with APP_LOCK:
        web_krakes = [k.to_dict() for k in WEB_KRAKES.values()]
        hardware = list(HARDWARE_KRAKES)

    return render_template(
        "krakes.html",
        web_krakes=web_krakes,
        hardware_krakes=hardware,
        annunciators=annunciators,
    )


@app.route("/krakes/spawn", methods=["POST"])
def spawn_krake():
    cfg = load_cfg()
    name = (request.form.get("name") or "").strip()
    annunciator_topic = (request.form.get("annunciator_topic") or "").strip()

    if not annunciator_topic:
        annunciators = get_cfg_annunciators(cfg)
        if annunciators:
            annunciator_topic = annunciators[0]
        else:
            annunciator_topic = "adam/out/annunciator"

    krake_id = uuid.uuid4().hex[:8].upper()
    krake = WebKrake(krake_id=krake_id, name=name or f"WebKrake-{krake_id}", annunciator_topic=annunciator_topic, cfg=cfg)

    with APP_LOCK:
        WEB_KRAKES[krake_id] = krake

    subscribe_topic_if_needed(annunciator_topic)
    append_app_log(f"Spawned web krake {krake_id} on {annunciator_topic}")
    return redirect(url_for("krakes"))


@app.route("/krakes/register-hardware", methods=["POST"])
def register_hardware_krake():
    name = (request.form.get("name") or "").strip()
    mac_address = (request.form.get("mac_address") or "").strip()
    mqtt_topic = (request.form.get("mqtt_topic") or "").strip()

    item = {
        "name": name,
        "mac_address": mac_address,
        "mqtt_topic": mqtt_topic,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    with APP_LOCK:
        HARDWARE_KRAKES.append(item)
        save_hardware_krakes(HARDWARE_KRAKES)

    append_app_log(f"Registered hardware krake name={name} mac={mac_address} topic={mqtt_topic}")
    return redirect(url_for("krakes"))


@app.route("/krakes/<krake_id>/action", methods=["POST"])
def krake_action(krake_id: str):
    action = (request.form.get("action") or "").strip().lower()

    with APP_LOCK:
        krake = WEB_KRAKES.get(krake_id)

    if krake is None:
        return redirect(url_for("krakes"))

    krake.apply_action(action)
    return redirect(url_for("krakes"))


@app.route("/api/krakes")
def api_krakes():
    with APP_LOCK:
        items = [k.to_dict() for k in WEB_KRAKES.values()]
    return jsonify(items)


@app.route("/api/log-events")
def api_log_events():
    lines = read_last_lines(LOG_FILE, 250)
    events = build_log_events(lines)
    return jsonify(events)


init_state()

if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)