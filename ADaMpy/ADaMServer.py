# ============================================================

# ============================================================

import json
import os
import time
import threading
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum

import paho.mqtt.client as mqtt
from ADaMpy.gpad_api import (
    encode_gpad_alarm,
    decode_gpad_alarm,
    encode_gpad_ack,
    decode_gpad_ack,
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_config() -> dict:
    # ADaMpy directory (this file lives in ADaMpy/)
    adam_py_dir = os.path.abspath(os.path.dirname(__file__))

    candidates = [
        os.path.join(adam_py_dir, "config", "adam_config.json"),
        os.path.join(adam_py_dir, "adam_config.json"),
        os.path.join(os.path.dirname(adam_py_dir), "config", "adam_config.json"),
        os.path.join(os.path.dirname(adam_py_dir), "adam_config.json"),
        os.path.join(os.getcwd(), "ADaMpy", "config", "adam_config.json"),
        os.path.join(os.getcwd(), "config", "adam_config.json"),
        os.path.join(os.getcwd(), "adam_config.json"),
    ]

    for path in candidates:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8-sig") as f:
                return json.load(f)

    raise FileNotFoundError(
        "Could not find adam_config.json. Expected at ADaMpy/config/adam_config.json."
    )


class Severity(IntEnum):
    UNKNOWN = 0
    ONE = 1
    TWO = 2
    THREE = 3
    FOUR = 4
    FIVE = 5


@dataclass
class AlarmRecord:
    alarm_id: str
    severity: int
    description: str
    source: str
    timestamp: str
    received_at: str
    seq: int
    status: str  # "active" or "acknowledged"
    sent_to: set[str] = field(default_factory=set)
    acked_by: set[str] = field(default_factory=set)


@dataclass
class AnnunciatorState:
    current_alarm_id: str | None = None
    current_sent_at_ts: float | None = None


class AlarmStrategy:
    name = "POLICY0"

    def pick_alarm_id(self, active_alarms, now_ts, current_alarm_id, current_sent_at_ts, pause_seconds):
        if not active_alarms:
            return None
        best = sorted(active_alarms, key=lambda a: a.seq)[-1]
        return best.alarm_id


class SeverityStrategy(AlarmStrategy):
    name = "SEVERITY"

    def pick_alarm_id(self, active_alarms, now_ts, current_alarm_id, current_sent_at_ts, pause_seconds):
        if not active_alarms:
            return None
        best = sorted(active_alarms, key=lambda a: (-int(a.severity), a.seq))[0]
        return best.alarm_id


class SeverityPauseStrategy(AlarmStrategy):
    name = "SEVERITY_PAUSE"

    def pick_alarm_id(self, active_alarms, now_ts, current_alarm_id, current_sent_at_ts, pause_seconds):
        # Mandatory pause before any rewrite. Pause still applies even after ACK.
        if current_alarm_id and current_sent_at_ts is not None:
            age = now_ts - float(current_sent_at_ts)
            if age < float(pause_seconds):
                return current_alarm_id

        if not active_alarms:
            return None

        best = sorted(active_alarms, key=lambda a: (-int(a.severity), a.seq))[0]
        return best.alarm_id


POLICIES = {
    "POLICY0": AlarmStrategy(),
    "SEVERITY": SeverityStrategy(),
    "SEVERITY_PAUSE": SeverityPauseStrategy(),
}


class ADaMServer:
    def __init__(self, cfg: dict):
        self.cfg = cfg

        self.broker_host = cfg.get("broker_host", "public.cloud.shiftr.io")
        self.broker_port = int(cfg.get("broker_port", 1883))
        self.username = cfg.get("username", "public")
        self.password = cfg.get("password", "public")

        self.alarm_topic = cfg.get("alarm_topic", "adam/in/alarms")
        self.ack_topic = cfg.get("ack_topic", "adam/acks")

        self.annunciators = list(cfg.get("annunciators", []))

        # Optional: avoid duplicate alarms in Krake by only sending to the first annunciator
        # Values: "all" (default), "first"
        self.broadcast_mode = str(cfg.get("broadcast_mode", "all")).strip().lower()
        if self.broadcast_mode in ("first", "single"):
            self.out_topics = self.annunciators[:1]
        else:
            self.out_topics = list(self.annunciators)

        self.pause_seconds = float(cfg.get("pause_seconds", 20.0))
        self.policy_name = str(cfg.get("policy", "SEVERITY_PAUSE")).strip().upper()
        self.strategy = POLICIES.get(self.policy_name, POLICIES["SEVERITY_PAUSE"])

        # Critical: tick loop so pause expiration actually advances without extra user input
        self.tick_seconds = float(cfg.get("tick_seconds", 0.5))

        self._lock = threading.Lock()
        self._stop = threading.Event()

        self.seq_counter = 0
        self.alarms_by_id: dict[str, AlarmRecord] = {}
        self.ann_state: dict[str, AnnunciatorState] = {t: AnnunciatorState() for t in self.out_topics}

        # ---------- LOGGING ----------
        self.logger = logging.getLogger("ADaMServer")
        self.logger.setLevel(logging.INFO)

        fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")

        if not self.logger.handlers:
            log_path = os.path.join(os.path.dirname(__file__), "adam_server.log")
            fh = logging.FileHandler(log_path, mode="a", encoding="utf-8")
            fh.setFormatter(fmt)
            self.logger.addHandler(fh)

            sh = logging.StreamHandler()
            sh.setFormatter(fmt)
            self.logger.addHandler(sh)

        # ---------- MQTT ----------
        self.client = mqtt.Client(
            client_id=f"ADaMServer-{uuid.uuid4().hex[:6]}",
            callback_api_version=mqtt.CallbackAPIVersion.VERSION1,
        )
        if self.username and self.password:
            self.client.username_pw_set(self.username, self.password)

        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

    def log(self, msg: str) -> None:
        self.logger.info(msg)

    # ---------------- MQTT callbacks ----------------
    def on_connect(self, client, userdata, flags, reason_code, properties=None):
        self.log(f"[ADaM] CONNECT rc={reason_code}")
        client.subscribe(self.alarm_topic, qos=1)
        client.subscribe(self.ack_topic, qos=1)
        self.log(f"[ADaM] Subscribed alarm_topic={self.alarm_topic} ack_topic={self.ack_topic}")
        self.log(f"[ADaM] Policy={self.policy_name} pause_seconds={self.pause_seconds}")
        self.log(f"[ADaM] Annunciators(all)={self.annunciators}")
        self.log(f"[ADaM] OutTopics(send)={self.out_topics} broadcast_mode={self.broadcast_mode}")
        self.log(f"[ADaM] Broker={self.broker_host}:{self.broker_port} user={self.username}")
        self.log(f"[ADaM] Tick={self.tick_seconds}s")

    def on_message(self, _client, _userdata, msg):
        payload = msg.payload.decode("utf-8", errors="replace")
        if msg.topic == self.alarm_topic:
            self.handle_alarm(payload)
        elif msg.topic == self.ack_topic:
            self.handle_ack(payload)

    # ---------------- Helpers ----------------
    def _resolve_alarm_id(self, alarm_id_hint: str, annunciator: str) -> str | None:
        hint = (alarm_id_hint or "").strip()
        if not hint:
            st = self.ann_state.get(annunciator)
            return st.current_alarm_id if st else None

        # Exact match
        with self._lock:
            if hint in self.alarms_by_id:
                return hint

            # If Krake sent a short prefix (like 98a82c05-8), match by prefix
            matches = [aid for aid in self.alarms_by_id.keys() if aid.startswith(hint)]
            if len(matches) == 1:
                return matches[0]

            # If multiple matches, prefer the current alarm for that annunciator
            st = self.ann_state.get(annunciator)
            if st and st.current_alarm_id and st.current_alarm_id.startswith(hint):
                return st.current_alarm_id

        return None

    def _format_alarm_text(self, alarm: AlarmRecord) -> str:
        # FIX: Put full alarm_id first so Krake can ACK the correct id reliably
        desc = (alarm.description or "").strip() or "NO DESCRIPTION"
        # Keep it reasonably short for display
        desc = desc[:40]
        return f"{alarm.alarm_id} {desc}"

    # ---------------- Alarm handling ----------------
    def handle_alarm(self, payload: str) -> None:
        raw = (payload or "").strip("\r\n")
        severity = 0
        description = ""
        source = ""
        timestamp = ""

        # Preferred format: GPAD_API
        try:
            g = decode_gpad_alarm(raw)
            severity = int(g.severity)
            description = g.description
            source = "gpad_api"
            timestamp = utc_now_iso()
            alarm_id = str(uuid.uuid4())
        except Exception:
            # Legacy JSON (deprecated)
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                self.log("[ADaM] RECEIVE ALARM invalid_payload (expected GPAD_API)")
                return

            self.log("[ADaM] RECEIVE ALARM json_deprecated")
            alarm_id = str(data.get("alarm_id") or "").strip() or str(uuid.uuid4())
            try:
                severity = int(data.get("severity") or 0)
            except (TypeError, ValueError):
                severity = 0
            description = str(data.get("description") or "")
            source = str(data.get("source") or "")
            timestamp = str(data.get("timestamp") or "")

        with self._lock:
            self.seq_counter += 1
            rec = AlarmRecord(
                alarm_id=alarm_id,
                severity=severity,
                description=description,
                source=source,
                timestamp=timestamp,
                received_at=utc_now_iso(),
                seq=self.seq_counter,
                status="active",
            )
            self.alarms_by_id[alarm_id] = rec

        self.log(f"[ADaM] RECEIVE ALARM id={alarm_id} sev={severity} desc={description[:60]}")
        self.evaluate_and_send_all()

    # ---------------- ACK handling ----------------
    def handle_ack(self, payload: str) -> None:
        raw = (payload or "").strip("\r\n")
        annunciator = ""
        status = ""
        alarm_id_hint = ""

        # Preferred format
        try:
            ack = decode_gpad_ack(raw)
            annunciator = (ack.annunciator or "").strip()
            status = (ack.status or "").strip().lower()
            alarm_id_hint = (ack.alarm_id or "").strip()
        except Exception:
            # Legacy JSON (deprecated)
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                self.log("[ADaM] RECEIVE ACK invalid_payload")
                return

            self.log("[ADaM] RECEIVE ACK json_deprecated")
            annunciator = str(data.get("annunciator") or "").strip()
            status = str(data.get("status") or "").strip().lower()
            alarm_id_hint = str(data.get("alarm_id") or "").strip()

        if annunciator and annunciator not in self.ann_state:
            self.log(f"[ADaM] RECEIVE ACK unknown_annunciator={annunciator} status={status}")
            return

        alarm_id = self._resolve_alarm_id(alarm_id_hint, annunciator) if annunciator else None

        self.log(
            f"[ADaM] RECEIVE ACK annunciator={annunciator or 'unknown'} "
            f"status={status} alarm_id={alarm_id or alarm_id_hint or ''}"
        )

        if status != "acknowledged":
            return
        if not annunciator or not alarm_id:
            return

        with self._lock:
            alarm = self.alarms_by_id.get(alarm_id)
            if not alarm:
                self.log(f"[ADaM] ACK for unknown alarm_id={alarm_id}")
                return

            alarm.acked_by.add(annunciator)

            required = set(alarm.sent_to) if alarm.sent_to else set(self.out_topics)
            if alarm.acked_by.issuperset(required):
                alarm.status = "acknowledged"

        self.evaluate_and_send_all()

    # ---------------- Views ----------------
    def _sort_key_for_view(self, a: AlarmRecord):
        if self.policy_name in ("SEVERITY", "SEVERITY_PAUSE"):
            return (-int(a.severity), a.seq)
        return (a.seq,)

    def get_active_view(self) -> list[AlarmRecord]:
        with self._lock:
            active = [a for a in self.alarms_by_id.values() if a.status == "active"]
            return sorted(active, key=self._sort_key_for_view)

    def get_all_view(self) -> list[AlarmRecord]:
        with self._lock:
            all_alarms = list(self.alarms_by_id.values())
            return sorted(all_alarms, key=self._sort_key_for_view)

    def print_view(self, rows: list[AlarmRecord]) -> None:
        print("\n--- Alarms ---")
        if not rows:
            print("(none)")
        else:
            for a in rows[:50]:
                print(f"{a.seq:04d} {a.alarm_id[:10]} sev={a.severity} status={a.status} desc={a.description}")
        print("-------------\n")

    def print_current(self) -> None:
        now_ts = time.time()
        with self._lock:
            rows = []
            for topic, st in self.ann_state.items():
                age = None
                if st.current_sent_at_ts is not None:
                    age = now_ts - float(st.current_sent_at_ts)
                rows.append((topic, st.current_alarm_id, age))

        print("\n--- Current per annunciator ---")
        for topic, alarm_id, age in rows:
            age_s = f"{age:.1f}s" if age is not None else "-"
            print(f"{topic} -> current={alarm_id or '-'} age={age_s}")
        print("--------------------------------\n")

    # ---------------- Policy evaluation & sending ----------------
    def _evaluate_and_send_for_topic(self, topic: str, active: list[AlarmRecord], now_ts: float) -> None:
        to_publish = None
        log_line = None

        with self._lock:
            st = self.ann_state[topic]

            # If current is acknowledged and pause has elapsed, allow clearing so next can be chosen
            if st.current_alarm_id:
                cur = self.alarms_by_id.get(st.current_alarm_id)
                if cur and cur.status == "acknowledged" and st.current_sent_at_ts is not None:
                    age = now_ts - float(st.current_sent_at_ts)
                    if age >= float(self.pause_seconds):
                        st.current_alarm_id = None
                        st.current_sent_at_ts = None

            next_alarm_id = self.strategy.pick_alarm_id(
                active,
                now_ts,
                st.current_alarm_id,
                st.current_sent_at_ts,
                self.pause_seconds,
            )

            if not next_alarm_id:
                return
            if next_alarm_id == st.current_alarm_id:
                return

            alarm = self.alarms_by_id.get(next_alarm_id)
            if not alarm or alarm.status != "active":
                return

            text = self._format_alarm_text(alarm)
            protocol = encode_gpad_alarm(alarm.severity, text)

            st.current_alarm_id = next_alarm_id
            st.current_sent_at_ts = now_ts

            alarm.sent_to.add(topic)

            to_publish = (topic, protocol)
            log_line = (
                f"[ADaM] SEND ALARM annunciator={topic} id={next_alarm_id} "
                f"sev={alarm.severity} policy={self.policy_name}"
            )

        if to_publish:
            self.client.publish(to_publish[0], to_publish[1], qos=1)
        if log_line:
            self.log(log_line)

    def evaluate_and_send_all(self) -> None:
        now_ts = time.time()
        with self._lock:
            active = [a for a in self.alarms_by_id.values() if a.status == "active"]

        for topic in self.out_topics:
            self._evaluate_and_send_for_topic(topic, active, now_ts)

    def policy_tick_loop(self) -> None:
        # This is what makes "after 20 sec, advance automatically" actually happen.
        while not self._stop.is_set():
            try:
                self.evaluate_and_send_all()
            except Exception as e:
                self.log(f"[ADaM] Tick error: {e}")
            time.sleep(self.tick_seconds)

    # ---------------- CLI ----------------
    def cli_loop(self) -> None:
        print("\n[ADaM] Server CLI ready. Type 'help' for commands.\n")
        while not self._stop.is_set():
            try:
                cmd = input("adam> ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                self._stop.set()
                break

            if cmd in ("help", "?"):
                print("Commands: help, list, list all, cur, exit")
            elif cmd == "list":
                self.print_view(self.get_active_view())
            elif cmd == "list all":
                self.print_view(self.get_all_view())
            elif cmd == "cur":
                self.print_current()
            elif cmd in ("exit", "quit"):
                self._stop.set()
            elif cmd == "":
                continue
            else:
                print("Unknown command. Try: help, list, list all, cur, exit")

    # ---------------- Runner ----------------
    def run_forever(self) -> None:
        self.client.connect(self.broker_host, self.broker_port)
        self.client.loop_start()

        tick_thread = threading.Thread(target=self.policy_tick_loop, daemon=True)
        tick_thread.start()

        try:
            while not self._stop.is_set():
                time.sleep(0.25)
        finally:
            self.client.loop_stop()
            self.client.disconnect()
            self.log("[ADaM] Stopped")


def main():
    cfg = load_config()
    srv = ADaMServer(cfg)
    t = threading.Thread(target=srv.cli_loop, daemon=True)
    t.start()
    srv.run_forever()


if __name__ == "__main__":
    main()


# ============================================================
# Rob / Forrest reference code — DO NOT TOUCH (KEEP COMMENTED)
# ============================================================

# `mac_to_NameDict.set("F4650BC0B52C", "KRAKE_US0006");
# // Make MAC to Serial number association in this dictionary
# StringDict mac_to_NameDict = new StringDict();
# void setupDictionary() {
#
#   mac_to_NameDict.set("F024F9F1B874", "KRAKE_LB0001");
#   mac_to_NameDict.set("142B2FEB1F00", "KRAKE_LB0002");
#   mac_to_NameDict.set("142B2FEB1C64", "KRAKE_LB0003");
#   mac_to_NameDict.set("142B2FEB1E24", "KRAKE_LB0004");
#   mac_to_NameDict.set("F024F9F1B880", "KRAKE_LB0005");
#
#   mac_to_NameDict.set("F4650BC0B52C", "KRAKE_US0006");
#   mac_to_NameDict.set("ECC9FF7D8EE8", "KRAKE_US0005");
#   mac_to_NameDict.set("ECC9FF7D8EF4", "KRAKE_US0004");
#   mac_to_NameDict.set("ECC9FF7C8C98", "KRAKE_US0003");
#   mac_to_NameDict.set("ECC9FF7D8F00", "KRAKE_US0002");
#   mac_to_NameDict.set("ECC9FF7C8BDC", "KRAKE_US0001");
#   mac_to_NameDict.set("3C61053DF08C", "20240421_USA1");
#   mac_to_NameDict.set("3C6105324EAC", "20240421_USA2");
#   mac_to_NameDict.set("3C61053DF63C", "20240421_USA3");
#   mac_to_NameDict.set("10061C686A14", "20240421_USA4");
#   mac_to_NameDict.set("FCB467F4F74C", "20240421_USA5");
#   mac_to_NameDict.set("CCDBA730098C", "20240421_LEB1");
#   mac_to_NameDict.set("CCDBA730BFD4", "20240421_LEB2");
#   mac_to_NameDict.set("CCDBA7300954", "20240421_LEB3");
#   mac_to_NameDict.set("A0DD6C0EFD28", "20240421_LEB4");
#   mac_to_NameDict.set("10061C684D28", "20240421_LEB5");
#   mac_to_NameDict.set("A0B765F51E28", "MockingKrake_LEB");
#   mac_to_NameDict.set("3C61053DC954", "Not Homework2, Maryville TN");
# }//end setup mac_to_NameDict

# TOPIC = "F4650BC0B52C_ALM"
