
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





import json
import os
import time
import threading
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import IntEnum

import paho.mqtt.client as mqtt


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_config() -> dict:
    base_dir = os.path.dirname(__file__)
    candidates = [
        os.path.join(base_dir, "config", "adam_config.json"),
        os.path.join(base_dir, "adam_config.json"),
    ]
    for path in candidates:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8-sig") as f:
                return json.load(f)
    raise FileNotFoundError("Could not find adam_config.json in ./config or current directory")


def to_krake_protocol(severity: int, text: str, width: int = 80) -> str:
    sev = int(severity) if severity is not None else 0
    if sev < 0:
        sev = 0
    if sev > 5:
        sev = 5
    body = (text or "")[:width]
    body = body.ljust(width, ".")
    return f"a{sev}{body}\n"


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
    status: str = "active"  # "active" | "acknowledged"


@dataclass
class AnnunciatorState:
    current_alarm_id: str | None = None
    current_sent_at_ts: float | None = None


# ============================================================
# Strategy Pattern (Gang-of-four)
# ============================================================
class AlarmStrategy:
    name = "BASE"

    def pick_alarm_id(
        self,
        active_alarms: list[AlarmRecord],
        now_ts: float,
        current_alarm_id: str | None,
        current_sent_at_ts: float | None,
        pause_seconds: float,
    ) -> str | None:
        raise NotImplementedError


class Policy0Strategy(AlarmStrategy):
    name = "POLICY0"

    def pick_alarm_id(self, active_alarms, _now_ts, current_alarm_id, _current_sent_at_ts, _pause_seconds):
        if current_alarm_id:
            return current_alarm_id
        if not active_alarms:
            return None
        oldest = sorted(active_alarms, key=lambda a: a.seq)[0]
        return oldest.alarm_id


class SeverityStrategy(AlarmStrategy):
    name = "SEVERITY"

    def pick_alarm_id(self, active_alarms, _now_ts, _current_alarm_id, _current_sent_at_ts, _pause_seconds):
        if not active_alarms:
            return None
        best = sorted(active_alarms, key=lambda a: (-int(a.severity), a.seq))[0]
        return best.alarm_id


class SeverityPauseStrategy(AlarmStrategy):
    name = "SEVERITY_PAUSE"

    def pick_alarm_id(self, active_alarms, now_ts, current_alarm_id, current_sent_at_ts, pause_seconds):
        # Mandatory pause before any rewrite.
        # Your requirement: pause still applies even after ACK.
        if current_alarm_id and current_sent_at_ts is not None:
            age = now_ts - float(current_sent_at_ts)
            if age < float(pause_seconds):
                return current_alarm_id

        if not active_alarms:
            return None

        best = sorted(active_alarms, key=lambda a: (-int(a.severity), a.seq))[0]
        return best.alarm_id


def make_strategy(name: str) -> AlarmStrategy:
    n = (name or "POLICY0").upper()
    if n == "SEVERITY":
        return SeverityStrategy()
    if n == "SEVERITY_PAUSE":
        return SeverityPauseStrategy()
    return Policy0Strategy()


# ============================================================
# ADaM Server
# ============================================================
class ADaMServer:
    def __init__(self, cfg: dict):
        self.cfg = cfg

        # Broker config (no more constants in code)
        self.broker_host = cfg.get("broker_host", "public.cloud.shiftr.io")
        self.broker_port = int(cfg.get("broker_port", 1883))
        self.username = cfg.get("username", "public")
        self.password = cfg.get("password", "public")

        # Topics + annunciators
        self.alarm_topic = cfg.get("alarm_topic", "adam/in/alarms")
        self.ack_topic = cfg.get("ack_topic", "adam/acks")
        self.annunciators = list(cfg.get("annunciators", []))
        if not self.annunciators:
            raise RuntimeError("Config error: annunciators[] is empty")

        # Policy + pause
        self.policy_name = (cfg.get("policy") or "POLICY0").upper()
        self.pause_seconds = float(cfg.get("severity_pause_seconds", 20))
        self.tick_seconds = float(cfg.get("tick_seconds", 0.5))
        self.strategy = make_strategy(self.policy_name)

        # State
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self.seq_counter = 0
        self.alarms_by_id: dict[str, AlarmRecord] = {}
        self.ann_state: dict[str, AnnunciatorState] = {t: AnnunciatorState() for t in self.annunciators}

        # Logging
        self.logger = self._make_logger(cfg.get("log_file", "adam_server.log"))
        self.log(f"[ADaM] Started policy={self.policy_name} pause={self.pause_seconds}s")

        # MQTT
        self.client = mqtt.Client(client_id="ADaMServer")
        if self.username and self.password:
            self.client.username_pw_set(self.username, self.password)

        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

    def _make_logger(self, log_file: str) -> logging.Logger:
        logger = logging.getLogger("adam_server")
        logger.setLevel(logging.INFO)

        if not logger.handlers:
            fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")

            fh = logging.FileHandler(log_file, mode="a", encoding="utf-8")
            fh.setFormatter(fmt)
            logger.addHandler(fh)

            sh = logging.StreamHandler()
            sh.setFormatter(fmt)
            logger.addHandler(sh)

        return logger

    def log(self, msg: str) -> None:
        self.logger.info(msg)

    # ---------------- MQTT callbacks ----------------
    def on_connect(self, client, userdata, flags, reason_code, properties=None):
        client.subscribe(self.alarm_topic, qos=1)
        client.subscribe(self.ack_topic, qos=1)
        self.log(f"[ADaM] Subscribed alarm_topic={self.alarm_topic} ack_topic={self.ack_topic}")
        self.log(f"[ADaM] Annunciators={self.annunciators}")

    def on_message(self, _client, _userdata, msg):
        payload = msg.payload.decode("utf-8", errors="replace")
        if msg.topic == self.alarm_topic:
            self.handle_alarm(payload)
        elif msg.topic == self.ack_topic:
            self.handle_ack(payload)

    def handle_alarm(self, payload: str) -> None:
        try:
            # Instead of expecting payload to be JSON, decode a GPAD_API string.
            # str[0] == 'a' , lvl = int(str[1]), descr = str[2:82];
            data = json.loads(payload)
        except json.JSONDecodeError:
            self.log("[ADaM] RECEIVE ALARM invalid_json")
            return

        alarm_id = str(data.get("alarm_id") or "").strip()
        if not alarm_id:
            self.log("[ADaM] RECEIVE ALARM missing_alarm_id")
            return

        try:
            severity = int(data.get("severity") or 0)
        except (TypeError, ValueError):
            severity = 0

        description = str(data.get("description") or "")
        source = str(data.get("source") or "")
        timestamp = str(data.get("timestamp") or "")

        with self._lock:
            existing = self.alarms_by_id.get(alarm_id)
            if existing and existing.status == "active":
                self.log(f"[ADaM] RECEIVE ALARM duplicate_active id={alarm_id}")
                return

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

    def handle_ack(self, payload: str) -> None:
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            self.log("[ADaM] RECEIVE ACK invalid_json")
            return

        annunciator = str(data.get("annunciator") or "").strip()
        status = str(data.get("status") or "").strip().lower()
        alarm_id = str(data.get("alarm_id") or "").strip()

        with self._lock:
            if annunciator and annunciator not in self.ann_state:
                self.log(f"[ADaM] RECEIVE ACK unknown_annunciator={annunciator} status={status}")
                return

            if annunciator and not alarm_id:
                alarm_id = self.ann_state[annunciator].current_alarm_id or ""

        self.log(f"[ADaM] RECEIVE ACK annunciator={annunciator or 'unknown'} status={status} alarm_id={alarm_id}")

        if status != "acknowledged":
            return
        if not alarm_id:
            return

        with self._lock:
            alarm = self.alarms_by_id.get(alarm_id)
            if alarm:
                alarm.status = "acknowledged"

            # Your requirement: pause still applies after ACK.
            # So DO NOT clear current_alarm_id here.
            # We only clear it after pause expires inside evaluate_and_send_all().

        self.evaluate_and_send_all()

    # ---------------- Views & ordering for CLI ----------------
    def _sort_key_for_view(self, a: AlarmRecord):
        # Views should look like what policy cares about.
        if self.policy_name in ("SEVERITY", "SEVERITY_PAUSE"):
            return (-int(a.severity), a.seq)
        return (a.seq,)

    def get_active_view(self) -> list[AlarmRecord]:
        with self._lock:
            active = [a for a in self.alarms_by_id.values() if a.status == "active"]
        return sorted(active, key=self._sort_key_for_view)

    def get_all_view(self) -> list[AlarmRecord]:
        with self._lock:
            all_items = list(self.alarms_by_id.values())
        return sorted(all_items, key=self._sort_key_for_view)

    def print_view(self, items: list[AlarmRecord]) -> None:
        print("\n--- Alarms ---")
        for i, a in enumerate(items, 1):
            desc = (a.description or "").replace("\n", " ")
            if len(desc) > 60:
                desc = desc[:60] + "..."
            print(f"{i}) [{a.status}] sev={a.severity} seq={a.seq} id={a.alarm_id} desc={desc}")
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
    def _format_alarm_text(self, alarm: AlarmRecord) -> str:
        short_id = alarm.alarm_id[:10]
        desc = alarm.description.strip() or "NO DESCRIPTION"
        return f"{short_id} {desc}"

    def evaluate_and_send_all(self) -> None:
        now_ts = time.time()

        with self._lock:
            active = [a for a in self.alarms_by_id.values() if a.status == "active"]


        for topic in self.annunciators:
            with self._lock:
                st = self.ann_state[topic]

                # If current alarm is acknowledged:
                # - In SEVERITY_PAUSE, keep showing it until pause expires, then clear
                # - In other policies, clear immediately
                if st.current_alarm_id:
                    cur = self.alarms_by_id.get(st.current_alarm_id)
                    if not cur:
                        st.current_alarm_id = None
                        st.current_sent_at_ts = None
                    elif cur.status != "active":
                        if self.policy_name == "SEVERITY_PAUSE" and st.current_sent_at_ts is not None:
                            age = now_ts - float(st.current_sent_at_ts)
                            if age >= float(self.pause_seconds):
                                st.current_alarm_id = None
                                st.current_sent_at_ts = None
                        else:
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
                    continue
                if next_alarm_id == st.current_alarm_id:
                    continue

                alarm = self.alarms_by_id.get(next_alarm_id)
                if not alarm or alarm.status != "active":
                    continue

                text = self._format_alarm_text(alarm)
                protocol = to_krake_protocol(alarm.severity, text)

                self.client.publish(topic, protocol, qos=1)
                st.current_alarm_id = next_alarm_id
                st.current_sent_at_ts = now_ts

            self.log(f"[ADaM] SEND ALARM annunciator={topic} id={next_alarm_id} sev={alarm.severity} policy={self.policy_name}")

    # ---------------- CLI commands ----------------
    def cli_loop(self) -> None:
        print("\n[ADaM] Server CLI ready. Type 'help' for commands.\n")
        while not self._stop.is_set():
            try:
                cmd = input("adam> ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                self._stop.set()
                break

            if cmd in ("help", "?"):
                print("\nCommands:")
                print("  list        -> show ACTIVE alarms (policy order)")
                print("  list all    -> show ALL alarms (policy order)")
                print("  cur         -> show current alarm per annunciator")
                print("  exit        -> stop server\n")
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

        cli_thread = threading.Thread(target=self.cli_loop, daemon=True)
        cli_thread.start()

        try:
            while not self._stop.is_set():
                self.evaluate_and_send_all()
                time.sleep(self.tick_seconds)
        except KeyboardInterrupt:
            pass
        finally:
            self._stop.set()
            self.client.loop_stop()
            self.client.disconnect()
            self.log("[ADaM] Stopped")


def main():
    cfg = load_config()
    server = ADaMServer(cfg)
    server.run_forever()


if __name__ == "__main__":
    main()
