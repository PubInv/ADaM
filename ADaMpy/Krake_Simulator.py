import json
import os
from datetime import datetime, timezone

import paho.mqtt.client as mqtt


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def clear_screen() -> None:
    print("\033[2J\033[H", end="")


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


class KrakeSimulator:
    def __init__(self, cfg: dict):
        self.sub_topic = cfg["annunciators"][0]
        self.ack_topic = cfg["ack_topic"]

        self.broker_host = cfg.get("broker_host", "public.cloud.shiftr.io")
        self.broker_port = int(cfg.get("broker_port", 1883))
        self.username = cfg.get("username", "public")
        self.password = cfg.get("password", "public")

        self.current_alarm_raw: str | None = None

        self.client = mqtt.Client(
            client_id="Krake_Simulator",
            callback_api_version=mqtt.CallbackAPIVersion.VERSION1,
        )
        if self.username and self.password:
            self.client.username_pw_set(self.username, self.password)

        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

    def on_connect(self, client, *_):
        client.subscribe(self.sub_topic, qos=1)
        print(f"[Krake] Subscribed to: {self.sub_topic}")
        print(f"[Krake] Publishing ACKs to: {self.ack_topic}")
        print("[Krake] Commands: ack, exit")

    def publish_ack(self, status: str) -> None:
        payload = {
            "annunciator": self.sub_topic,
            "status": status,
            "ack_at": utc_now_iso(),
        }
        self.client.publish(self.ack_topic, json.dumps(payload), qos=1)

    def on_message(self, _client, _userdata, msg):
        raw = msg.payload.decode("utf-8", errors="replace")
        self.current_alarm_raw = raw

        clear_screen()
        print(raw, end="")

        self.publish_ack("received")

    def run(self) -> None:
        self.client.connect(self.broker_host, self.broker_port)
        self.client.loop_start()

        try:
            while True:
                cmd = input("> ").strip().lower()
                if cmd == "ack":
                    if not self.current_alarm_raw:
                        print("No alarm displayed")
                        continue
                    self.publish_ack("acknowledged")
                elif cmd == "exit":
                    break
                elif cmd == "":
                    continue
                else:
                    print("Unknown command. Use: ack, exit")
        finally:
            self.client.loop_stop()
            self.client.disconnect()


def main():
    cfg = load_config()
    if not cfg.get("annunciators"):
        raise RuntimeError("annunciators[] is empty in config")
    KrakeSimulator(cfg).run()


if __name__ == "__main__":
    main()
