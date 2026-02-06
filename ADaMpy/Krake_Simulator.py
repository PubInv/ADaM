from __future__ import annotations

import os
import queue
import sys
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_config() -> dict:
    import json

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


def parse_gpad_alarm(payload: str) -> tuple[int, str, str]:
    """
    Expected formats you are actually seeing:
      a4a7a73c11-1 legisbleeding
      a5c04b65c8-7 heartstroke

    Rule:
      payload[0] == 'a'
      payload[1] is severity digit
      then alarm_id until first space
      rest is text
    """
    s = payload.strip()

    if len(s) >= 3 and s[0] == "a" and s[1].isdigit():
        sev = int(s[1])
        rest = s[2:].strip()
        if not rest:
            # No id, no text, fallback
            return sev, str(abs(hash(s))), ""
        if " " in rest:
            alarm_id, text = rest.split(" ", 1)
            return sev, alarm_id.strip(), text.strip()
        return sev, rest.strip(), ""
    # Fallback, still dedup across topics because it does NOT include topic
    return 0, str(abs(hash(s))), s


def make_ack_payload(annunciator: str, status: str, alarm_id: str) -> str:
    # Matches what sniff_mqtt showed:
    # k|<annunciator>|<status>|<alarm_id>|<timestamp>
    return f"k|{annunciator}|{status}|{alarm_id}|{utc_now_iso()}"


class Krake:
    def __init__(self, cfg: dict):
        self.cfg = cfg

        self.annunciators = list(cfg.get("annunciators", []))
        if not self.annunciators:
            raise RuntimeError("config annunciators[] is empty")

        self.ack_topic = cfg.get("ack_topic", "adam/acks")

        self.host = cfg.get("broker_host", "public.cloud.shiftr.io")
        self.port = int(cfg.get("broker_port", 1883))

        # You already learned this the hard way: public / public
        self.username = cfg.get("username", "public")
        self.password = cfg.get("password", "public")

        self.events: queue.Queue[tuple[str, str, int, str, str]] = queue.Queue()

        # Track what each topic currently shows
        self.current_by_topic: dict[str, str] = {}

        # Dedup display state
        self.display_alarm_id: str | None = None
        self.display_payload: str = ""
        self.display_sev: int = 0
        self.display_sources: set[str] = set()

        self._printed_banner = False

        self.client = self._make_client()

    def _make_client(self) -> mqtt.Client:
        kwargs = {"client_id": f"Krake_Simulator_{os.getpid()}"}
        try:
            kwargs["callback_api_version"] = mqtt.CallbackAPIVersion.VERSION2
        except Exception:
            pass

        c = mqtt.Client(**kwargs)
        if self.username and self.password:
            c.username_pw_set(self.username, self.password)

        c.on_connect = self.on_connect
        c.on_message = self.on_message
        return c

    def on_connect(self, client, userdata, flags, reason_code, properties=None):
        for t in self.annunciators:
            client.subscribe(t, qos=1)
        # Do not print here, enqueue a banner event handled by main loop
        self.events.put(("_SYSTEM_", "_CONNECTED_", 0, "", ""))

    def on_message(self, client, userdata, msg):
        topic = msg.topic
        payload = msg.payload.decode("utf-8", errors="replace").rstrip("\n")

        sev, alarm_id, _text = parse_gpad_alarm(payload)

        self.current_by_topic[topic] = alarm_id

        # Auto "received" ACK for this topic with the alarm_id
        ack = make_ack_payload(topic, "received", alarm_id)
        client.publish(self.ack_topic, ack, qos=1)

        # Main thread prints and dedupes
        self.events.put((topic, alarm_id, sev, payload, payload))

    def print_alarm_once(self):
        print("\n" + "=" * 70)
        print(self.display_payload)
        if self.display_sources:
            srcs = ", ".join(sorted(self.display_sources))
            print("-" * 70)
            print(f"sources: {srcs}")
        print("=" * 70)
        print("> ", end="", flush=True)

    def send_ack_current(self):
        if not self.display_alarm_id:
            print("\nNo alarm to ack")
            print("> ", end="", flush=True)
            return

        alarm_id = self.display_alarm_id

        # Ack all topics that currently show this alarm_id
        targets = [t for t in self.annunciators if self.current_by_topic.get(t) == alarm_id]
        if not targets:
            # Fallback: still ack all configured annunciators for this alarm_id
            targets = self.annunciators[:]

        for t in targets:
            ack = make_ack_payload(t, "acknowledged", alarm_id)
            self.client.publish(self.ack_topic, ack, qos=1)

        print(f"\nACK sent for alarm_id={alarm_id} to {len(targets)} topic(s)")
        print("> ", end="", flush=True)

    def run(self):
        self.client.connect(self.host, self.port)
        self.client.loop_start()

        try:
            import msvcrt
        except Exception:
            msvcrt = None

        cmd_buf = ""

        print("> ", end="", flush=True)

        try:
            while True:
                # Drain MQTT events
                while True:
                    try:
                        topic, alarm_id, sev, payload, _raw = self.events.get_nowait()
                    except queue.Empty:
                        break

                    if topic == "_SYSTEM_" and alarm_id == "_CONNECTED_":
                        if not self._printed_banner:
                            self._printed_banner = True
                            print("\n[Krake] Connected")
                            print(f"[Krake] Broker: {self.host}:{self.port} user={self.username}")
                            print("[Krake] Subscribed to topics:")
                            for t in self.annunciators:
                                print(f"  - {t}")
                            print(f"[Krake] Publishing ACKs to: {self.ack_topic}")
                            print("[Krake] Commands: ack, exit")
                            print("> ", end="", flush=True)
                        continue

                    # Dedup rule: print only when alarm_id changes OR severity changes for same alarm
                    if (self.display_alarm_id != alarm_id) or (self.display_alarm_id == alarm_id and sev != self.display_sev):
                        self.display_alarm_id = alarm_id
                        self.display_sev = sev
                        self.display_payload = payload
                        self.display_sources = {topic}
                        self.print_alarm_once()
                    else:
                        # Same alarm, just add source, do not print again
                        self.display_sources.add(topic)

                # Read commands
                if msvcrt is None:
                    cmd = input().strip().lower()
                    if cmd == "ack":
                        self.send_ack_current()
                    elif cmd == "exit":
                        return
                    elif cmd == "":
                        print("> ", end="", flush=True)
                    else:
                        print("\nUnknown command. Use: ack, exit")
                        print("> ", end="", flush=True)
                    continue

                if msvcrt.kbhit():
                    ch = msvcrt.getwch()

                    if ch in ("\r", "\n"):
                        cmd = cmd_buf.strip().lower()
                        cmd_buf = ""
                        print("")  # newline

                        if cmd == "ack":
                            self.send_ack_current()
                        elif cmd == "exit":
                            return
                        elif cmd == "":
                            print("> ", end="", flush=True)
                        else:
                            print("Unknown command. Use: ack, exit")
                            print("> ", end="", flush=True)

                    elif ch == "\b":
                        if cmd_buf:
                            cmd_buf = cmd_buf[:-1]
                            sys.stdout.write("\b \b")
                            sys.stdout.flush()

                    else:
                        if len(ch) == 1 and ch.isprintable():
                            cmd_buf += ch
                            sys.stdout.write(ch)
                            sys.stdout.flush()

                time.sleep(0.03)

        finally:
            self.client.loop_stop()
            self.client.disconnect()


def main():
    cfg = load_config()
    Krake(cfg).run()


if __name__ == "__main__":
    main()
