# ============================================================
# ADaMServer.py
#
# Policies:
#   POLICY0        : FIFO, send as received, no pause
#   SEVERITY       : highest severity first, no pause
#   SEVERITY_PAUSE : highest severity first, enforce min seconds between sends
#
# Important assumption:
#   Krake holds ONE alarm at a time, so server never preempts a displayed alarm.
#
# GPAP spec: https://github.com/PubInv/gpap
# ============================================================

from __future__ import annotations

import json
import os
import time
import threading
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

from ADaMpy.gpad_api import (
    encode_gpap_alarm,
    decode_gpap_alarm,
    decode_gpap_response,
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_config() -> dict:
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
    raise FileNotFoundError("Could not find adam_config.json. Expected at ADaMpy/config/adam_config.json.")


OPEN_STATUSES = {"active", "acknowledged"}


@dataclass
class AlarmEvent:
    at: str
    annunciator: str
    action: str
    note: str = ""


@dataclass
class AlarmRecord:
    alarm_id: str
    msg_id: str
    severity: int
    text: str
    source: str
    received_at: str
    seq: int
    status: str = "active"

    shelved_until_ts: float | None = None

    sent_to: set[str] = field(default_factory=set)
    acked_by: set[str] = field(default_factory=set)
    history: list[AlarmEvent] = field(default_factory=list)


@dataclass
class AnnunciatorState:
    current_msg_id: str | None = None
    last_sent_at_ts: float | None = None
    muted: bool = False


class ADaMServer:
    def __init__(self, cfg: dict):
        self.cfg = cfg

        self.broker_host = cfg.get("broker_host", "public.cloud.shiftr.io")
        self.broker_port = int(cfg.get("broker_port", 1883))
        self.username = cfg.get("username", "public")
        self.password = cfg.get("password", "public")

        self.alarm_topic = cfg.get("alarm_topic", "adam/in/alarms")
        self.ack_topic_base = cfg.get("ack_topic", "adam/acks")

        self.annunciators = list(cfg.get("annunciators", []))
        if not self.annunciators:
            raise RuntimeError("config annunciators[] is empty")
        self.out_topics = list(self.annunciators)

        self.policy_name = str(cfg.get("policy", "SEVERITY_PAUSE")).strip().upper()

        self.pause_seconds = float(cfg.get("severity_pause_seconds", cfg.get("pause_seconds", 20.0)))
        self.shelve_seconds = float(cfg.get("shelve_seconds", cfg.get("shelve_minutes", 5) * 60.0))
        self.tick_seconds = float(cfg.get("tick_seconds", 0.5))

        self._lock = threading.Lock()
        self._stop = threading.Event()

        self.seq_counter = 0
        self.alarms_by_msg_id: dict[str, AlarmRecord] = {}
        self.ann_state: dict[str, AnnunciatorState] = {t: AnnunciatorState() for t in self.out_topics}

        self.logger = logging.getLogger("ADaMServer")
        self.logger.setLevel(logging.INFO)
        fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")

        if not self.logger.handlers:
            log_path = os.path.join(os.path.dirname(__file__), cfg.get("log_file", "adam_server.log"))
            fh = logging.FileHandler(log_path, mode="a", encoding="utf-8")
            fh.setFormatter(fmt)
            self.logger.addHandler(fh)

            sh = logging.StreamHandler()
            sh.setFormatter(fmt)
            self.logger.addHandler(sh)

        kwargs = {"client_id": f"ADaMServer-{uuid.uuid4().hex[:6]}"}
        try:
            kwargs["callback_api_version"] = mqtt.CallbackAPIVersion.VERSION2
        except Exception:
            pass

        self.client = mqtt.Client(**kwargs)
        if self.username and self.password:
            self.client.username_pw_set(self.username, self.password)

        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

    def log(self, msg: str) -> None:
        self.logger.info(msg)

    def on_connect(self, client, userdata, flags, reason_code, properties=None):
        client.subscribe(self.alarm_topic, qos=1)
        client.subscribe(f"{self.ack_topic_base}/#", qos=1)

        self.log(f"[ADaM] Connected rc={reason_code}")
        self.log(f"[ADaM] Alarm topic={self.alarm_topic}")
        self.log(f"[ADaM] Ack topic base={self.ack_topic_base} (subscribing to {self.ack_topic_base}/#)")
        self.log(f"[ADaM] Out topics={self.out_topics}")
        self.log(f"[ADaM] Policy={self.policy_name} pause={self.pause_seconds}s shelve={self.shelve_seconds}s")

    def on_message(self, _client, _userdata, msg):
        payload = msg.payload.decode("utf-8", errors="replace")

        if msg.topic == self.alarm_topic:
            self.handle_alarm(payload)
            return

        if msg.topic.startswith(self.ack_topic_base + "/"):
            self.handle_operator(payload, msg.topic)
            return

    def _new_msg_id(self) -> str:
        return uuid.uuid4().hex[:5].upper()

    def _annunciator_from_topic(self, topic: str) -> str | None:
        if topic.startswith(self.ack_topic_base + "/"):
            return topic[len(self.ack_topic_base) + 1 :]
        return None

    def _record_event(self, alarm: AlarmRecord, annunciator: str, action: str, note: str = "") -> None:
        alarm.history.append(AlarmEvent(at=utc_now_iso(), annunciator=annunciator, action=action, note=note))

    def _resolve_msg_id(self, msg_id_hint: str | None, annunciator: str) -> str | None:
        hint = (msg_id_hint or "").strip().upper()

        if hint:
            with self._lock:
                if hint in self.alarms_by_msg_id:
                    return hint
                matches = [mid for mid in self.alarms_by_msg_id.keys() if mid.startswith(hint)]
                if len(matches) == 1:
                    return matches[0]

        st = self.ann_state.get(annunciator)
        if st and st.current_msg_id:
            return st.current_msg_id

        return None

    def handle_alarm(self, payload: str) -> None:
        raw = (payload or "").strip("\r\n").strip()
        if not raw:
            self.log("[ADaM] RECEIVE ALARM empty_payload")
            return

        try:
            a = decode_gpap_alarm(raw)
            severity = int(a.severity)
            text = a.text
            msg_id = (a.msg_id or self._new_msg_id()).upper()
        except Exception:
            self.log("[ADaM] RECEIVE ALARM invalid_payload (expected GPAP)")
            return

        with self._lock:
            self.seq_counter += 1
            rec = AlarmRecord(
                alarm_id=str(uuid.uuid4()),
                msg_id=msg_id,
                severity=severity,
                text=text,
                source="gpap",
                received_at=utc_now_iso(),
                seq=self.seq_counter,
                status="active",
            )
            self.alarms_by_msg_id[msg_id] = rec

        self.log(f"[ADaM] RECEIVE ALARM msg_id={msg_id} sev={severity} text={text[:80]}")
        self.evaluate_and_send_all()

    def handle_operator(self, payload: str, topic: str) -> None:
        raw = (payload or "").strip("\r\n").strip()
        annunciator = self._annunciator_from_topic(topic)
        if not annunciator:
            return
        if annunciator not in self.ann_state:
            self.log(f"[ADaM] RECEIVE OP unknown_annunciator={annunciator} payload={raw[:120]}")
            return

        if raw in ("m", "u"):
            with self._lock:
                st = self.ann_state[annunciator]
                new_val = True if raw == "m" else False
                if st.muted != new_val:
                    st.muted = new_val
                    self.log(f"[ADaM] MUTE_CHANGE annunciator={annunciator} muted={st.muted}")
            return

        try:
            r = decode_gpap_response(raw)
            action = r.action
            msg_id_hint = r.msg_id
        except Exception:
            self.log(f"[ADaM] RECEIVE OP invalid_payload topic={topic} payload={raw[:120]}")
            return

        msg_id = self._resolve_msg_id(msg_id_hint, annunciator)
        if not msg_id:
            self.log(f"[ADaM] RECEIVE OP unknown_msg_id annunciator={annunciator} hint={msg_id_hint or ''}")
            return

        with self._lock:
            alarm = self.alarms_by_msg_id.get(msg_id)
            if not alarm:
                self.log(f"[ADaM] OP for unknown msg_id={msg_id}")
                return

            self._record_event(alarm, annunciator, action)

            if action == "a":
                alarm.acked_by.add(annunciator)
                alarm.status = "acknowledged" if alarm.status in OPEN_STATUSES else alarm.status

            elif action == "c":
                alarm.status = "completed"

            elif action == "d":
                alarm.status = "dismissed"

            elif action == "s":
                alarm.status = "shelved"
                alarm.shelved_until_ts = time.time() + float(self.shelve_seconds)
                alarm.acked_by.clear()
                alarm.sent_to.clear()

            else:
                self.log(f"[ADaM] OP invalid_action={action}")
                return

            self.log(f"[ADaM] OP action={action} annunciator={annunciator} msg_id={msg_id} status={alarm.status}")

            st = self.ann_state[annunciator]
            if st.current_msg_id == msg_id and action in ("c", "d", "s"):
                st.current_msg_id = None

        self.evaluate_and_send_all()

    def _unshelve_if_due(self) -> None:
        now = time.time()
        changed = False
        with self._lock:
            for alarm in self.alarms_by_msg_id.values():
                if alarm.status != "shelved":
                    continue
                if alarm.shelved_until_ts is None:
                    continue
                if now < float(alarm.shelved_until_ts):
                    continue

                alarm.status = "active"
                alarm.shelved_until_ts = None
                self.seq_counter += 1
                alarm.seq = self.seq_counter
                changed = True
                self.log(f"[ADaM] UNSHELVE msg_id={alarm.msg_id} -> active")

        if changed:
            self.evaluate_and_send_all()

    def _open_alarms(self) -> list[AlarmRecord]:
        return [a for a in self.alarms_by_msg_id.values() if a.status in OPEN_STATUSES]

    def _policy_sort_key(self, a: AlarmRecord):
        if self.policy_name == "POLICY0":
            return (a.seq,)
        if self.policy_name in ("SEVERITY", "SEVERITY_PAUSE"):
            return (-int(a.severity), a.seq)
        return (-int(a.severity), a.seq)

    def _pick_next(self, open_alarms: list[AlarmRecord]) -> AlarmRecord | None:
        if not open_alarms:
            return None
        return sorted(open_alarms, key=self._policy_sort_key)[0]

    def _can_send_now(self, st: AnnunciatorState, now_ts: float) -> bool:
        if self.policy_name != "SEVERITY_PAUSE":
            return True
        if st.last_sent_at_ts is None:
            return True
        age = now_ts - float(st.last_sent_at_ts)
        return age >= float(self.pause_seconds)

    def _send_to_annunciator(self, annunciator_topic: str, alarm: AlarmRecord, now_ts: float) -> None:
        payload = encode_gpap_alarm(alarm.severity, alarm.text, msg_id=alarm.msg_id, max_len=80)
        st = self.ann_state[annunciator_topic]

        st.current_msg_id = alarm.msg_id
        st.last_sent_at_ts = now_ts
        alarm.sent_to.add(annunciator_topic)

        self.client.publish(annunciator_topic, payload, qos=1)
        self.log(f"[ADaM] SEND ALARM annunciator={annunciator_topic} msg_id={alarm.msg_id} sev={alarm.severity}")

    def _evaluate_for_topic(self, topic: str, now_ts: float) -> None:
        candidate = None
        override_from_msg_id = None

        with self._lock:
            st = self.ann_state[topic]

            cur = None
            if st.current_msg_id:
                cur = self.alarms_by_msg_id.get(st.current_msg_id)

                # If current alarm is gone or no longer open, clear it
                if not (cur and cur.status in OPEN_STATUSES):
                    st.current_msg_id = None
                    cur = None

            open_alarms = self._open_alarms()
            if not open_alarms:
                return

            # Case 1: Nothing currently displayed -> send if pause allows
            if cur is None:
                if not self._can_send_now(st, now_ts):
                    return

                candidate = self._pick_next(open_alarms)
                if not candidate:
                    return

            # Case 2: Something is currently displayed
            else:
                # For POLICY0 / SEVERITY (no pause preemption), keep current until operator action
                if self.policy_name != "SEVERITY_PAUSE":
                    return

                # Still inside pause window, do not preempt yet
                if not self._can_send_now(st, now_ts):
                    return

                best = self._pick_next(open_alarms)
                if not best:
                    return

                # If current is already the best open alarm, no override needed
                if best.msg_id == cur.msg_id:
                    return

                # Only override if the new candidate has strictly higher priority
                # Lower sort key means higher priority in current policy implementation
                if self._policy_sort_key(best) < self._policy_sort_key(cur):
                    candidate = best
                    override_from_msg_id = cur.msg_id
                else:
                    return

        if candidate is not None:
            if override_from_msg_id:
                self.log(
                    f"[ADaM] OVERRIDE annunciator={topic} "
                    f"from_msg_id={override_from_msg_id} to_msg_id={candidate.msg_id} "
                    f"after_pause={self.pause_seconds}s"
                )
            self._send_to_annunciator(topic, candidate, now_ts)

    def evaluate_and_send_all(self) -> None:
        now_ts = time.time()
        for topic in self.out_topics:
            self._evaluate_for_topic(topic, now_ts)

    def tick_loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._unshelve_if_due()
                self.evaluate_and_send_all()
            except Exception as e:
                self.log(f"[ADaM] Tick error: {e}")
            time.sleep(self.tick_seconds)

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
                self.print_view(self.get_open_view())
            elif cmd == "list all":
                self.print_view(self.get_all_view())
            elif cmd == "cur":
                self.print_current()
            elif cmd in ("exit", "quit"):
                self._stop.set()

    def get_open_view(self) -> list[AlarmRecord]:
        with self._lock:
            rows = [a for a in self.alarms_by_msg_id.values() if a.status in OPEN_STATUSES]
            return sorted(rows, key=self._policy_sort_key)

    def get_all_view(self) -> list[AlarmRecord]:
        with self._lock:
            rows = list(self.alarms_by_msg_id.values())
            return sorted(rows, key=lambda a: a.seq)

    def print_view(self, rows: list[AlarmRecord]) -> None:
        print("\n--- Alarms ---")
        if not rows:
            print("(none)")
        else:
            for a in rows[:50]:
                print(f"{a.seq:04d} msg_id={a.msg_id} sev={a.severity} status={a.status} text={a.text[:60]}")
        print("-------------\n")

    def print_current(self) -> None:
        now_ts = time.time()
        with self._lock:
            print("\n--- Current per annunciator ---")
            for topic, st in self.ann_state.items():
                age = "-"
                pause_left = "-"
                if st.last_sent_at_ts is not None:
                    age_val = now_ts - float(st.last_sent_at_ts)
                    age = f"{age_val:.1f}s"
                    if self.policy_name == "SEVERITY_PAUSE":
                        pause_left = f"{max(0.0, float(self.pause_seconds) - age_val):.1f}s"
                print(
                    f"{topic} -> current={st.current_msg_id or '-'} "
                    f"age={age} pause_left={pause_left} muted={st.muted}"
                )
            print("--------------------------------\n")

    def run_forever(self) -> None:
        self.client.connect(self.broker_host, self.broker_port)
        self.client.loop_start()

        tick_thread = threading.Thread(target=self.tick_loop, daemon=True)
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
