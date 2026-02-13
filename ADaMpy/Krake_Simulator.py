from __future__ import annotations

import json
import os
import sys
import time
import threading
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

from ADaMpy.gpad_api import decode_gpap_alarm, encode_gpap_response


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_config() -> dict:
    base = os.path.abspath(os.path.dirname(__file__))
    candidates = [
        os.path.join(base, "config", "adam_config.json"),
        os.path.join(base, "adam_config.json"),
    ]
    for p in candidates:
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8-sig") as f:
                return json.load(f)
    raise FileNotFoundError("Could not find adam_config.json under ADaMpy/config or ADaMpy")


class KrakeSimulator:
    def __init__(self, cfg: dict, annunciator_topic: str):
        self.cfg = cfg
        self.annunciator_topic = annunciator_topic

        self.ack_topic_base = cfg.get("ack_topic", "adam/acks")
        self.ack_topic = f"{self.ack_topic_base}/{self.annunciator_topic}"

        self.host = cfg.get("broker_host", "public.cloud.shiftr.io")
        self.port = int(cfg.get("broker_port", 1883))
        self.username = cfg.get("username", "public")
        self.password = cfg.get("password", "public")

        # IMPORTANT: hold is ONLY for SEVERITY_PAUSE
        self.policy_name = str(cfg.get("policy", "")).strip().upper()
        if self.policy_name == "SEVERITY_PAUSE":
            self.pause_seconds = float(cfg.get("severity_pause_seconds", cfg.get("pause_seconds", 20.0)))
        else:
            self.pause_seconds = 0.0

        self.current_msg_id: str | None = None
        self.current_sev: int | None = None
        self.current_text: str = ""
        self.muted: bool = False

        # Hold state (starts when an alarm is displayed)
        self.hold_until_ts: float | None = None
        self.buffered_alarm: tuple[str | None, int, str] | None = None
        self._hold_timer: threading.Timer | None = None

        self._lock = threading.Lock()

        kwargs = {"client_id": f"KrakeSim-{os.getpid()}"}
        try:
            kwargs["callback_api_version"] = mqtt.CallbackAPIVersion.VERSION2
        except Exception:
            pass

        self.client = mqtt.Client(**kwargs)
        if self.username and self.password:
            self.client.username_pw_set(self.username, self.password)

        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

    def on_connect(self, client, userdata, flags, rc, properties=None):
        client.subscribe(self.annunciator_topic, qos=1)
        with self._lock:
            print(f"[Krake] Connected rc={rc}")
            print(f"[Krake] Subscribed to annunciator topic: {self.annunciator_topic}")
            print(f"[Krake] Publishing operator responses to: {self.ack_topic}")
            if self.pause_seconds > 0:
                print(f"[Krake] Display hold = {self.pause_seconds:.1f}s (policy=SEVERITY_PAUSE)")
            else:
                print(f"[Krake] Display hold disabled (policy={self.policy_name or 'UNKNOWN'})")
        self.print_help()

    def print_help(self):
        with self._lock:
            print(
                "\nKeys:\n"
                "  a = acknowledge\n"
                "  c = complete\n"
                "  d = dismiss\n"
                "  s = shelve\n"
                "  m = mute (project extension)\n"
                "  u = unmute (project extension)\n"
                "  h = help\n"
                "  q = quit\n"
            )
        self.prompt()

    def prompt(self):
        state = "MUTED" if self.muted else "UNMUTED"
        if self.current_msg_id:
            print(f"[Krake:{state}] msg_id={self.current_msg_id} > ", end="", flush=True)
        else:
            print(f"[Krake:{state}] > ", end="", flush=True)

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
        # Hold only when pause_seconds > 0 (SEVERITY_PAUSE)
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

            self.prompt()

    def _display_alarm(self, msg_id: str | None, sev: int, text: str) -> None:
        self.current_msg_id = (msg_id or "").upper() if msg_id else None
        self.current_sev = int(sev)
        self.current_text = text or ""

        print("\n" + "=" * 70)
        mid = self.current_msg_id or "(no msg_id)"
        print(f"ALARM sev={self.current_sev} msg_id={mid}")
        print(self.current_text)
        print("=" * 70)
        self.prompt()

    def on_message(self, client, userdata, msg):
        payload = msg.payload.decode("utf-8", errors="replace").strip("\r\n")

        try:
            a = decode_gpap_alarm(payload)
        except Exception:
            with self._lock:
                if self.current_msg_id:
                    print(f"\n[Krake] Ignoring non-GPAP payload: {payload[:120]}")
                    self.prompt()
            return

        msg_id = (a.msg_id or "").upper() if a.msg_id else None
        sev = int(a.severity)
        text = a.text

        with self._lock:
            # Only buffer when hold is enabled AND active
            if self.pause_seconds > 0 and self._in_hold():
                self.buffered_alarm = (msg_id, sev, text)
                return

            self.buffered_alarm = None
            self._display_alarm(msg_id, sev, text)
            self._begin_hold_now()

    def publish(self, payload: str):
        info = self.client.publish(self.ack_topic, payload, qos=1)
        with self._lock:
            if info.rc != 0:
                print(f"\n[Krake] Publish failed rc={info.rc}")
            else:
                print(f"\n[Krake] Sent: {payload}")
            self.prompt()

    def _clear_display_only(self, reason: str) -> None:
        self.current_msg_id = None
        self.current_sev = None
        self.current_text = ""
        with self._lock:
            print(f"\n[Krake] {reason}. Waiting for next alarm...")
            self.prompt()

    def run(self):
        self.client.connect(self.host, self.port)
        self.client.loop_start()

        try:
            while True:
                cmd = input().strip().lower()
                if not cmd:
                    self.prompt()
                    continue

                k = cmd[0]

                if k == "q":
                    break
                if k == "h":
                    self.print_help()
                    continue

                if k in ("a", "c", "d", "s"):
                    if not self.current_msg_id:
                        with self._lock:
                            print("\n[Krake] No active alarm. Ignoring action.")
                            self.prompt()
                        continue

                    payload = encode_gpap_response(k, self.current_msg_id)
                    self.publish(payload)

                    if k == "c":
                        self._clear_display_only("Completed current alarm")
                    elif k == "d":
                        self._clear_display_only("Dismissed current alarm")
                    elif k == "s":
                        self._clear_display_only("Shelved current alarm")
                    continue

                if k == "m":
                    self.muted = True
                    self.publish("m")
                    continue

                if k == "u":
                    self.muted = False
                    self.publish("u")
                    continue

                with self._lock:
                    print("\n[Krake] Unknown key. Press h for help.")
                    self.prompt()

        finally:
            self._cancel_hold_timer()
            self.client.loop_stop()
            self.client.disconnect()
            with self._lock:
                print("\n[Krake] Stopped")


def main():
    cfg = load_config()

    annunciator_topic = sys.argv[1].strip() if len(sys.argv) >= 2 else None
    if not annunciator_topic:
        annunciators = list(cfg.get("annunciators", []))
        if not annunciators:
            raise RuntimeError("config annunciators[] is empty")
        annunciator_topic = annunciators[0]

    sim = KrakeSimulator(cfg, annunciator_topic)
    sim.run()


if __name__ == "__main__":
    main()