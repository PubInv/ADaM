import os
import json
import uuid

import paho.mqtt.client as mqtt

from ADaMpy.gpad_api import encode_gpap_alarm


CFG_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config", "adam_config.json"))


def load_cfg() -> dict:
    with open(CFG_FILE, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def new_msg_id() -> str:
    return uuid.uuid4().hex[:5].upper()


def main():
    cfg = load_cfg()

    broker = cfg.get("broker_host", "public.cloud.shiftr.io")
    port = int(cfg.get("broker_port", 1883))
    user = cfg.get("username", "public")
    pw = cfg.get("password", "public")

    topic = cfg.get("alarm_topic", "adam/in/alarms")

    client = mqtt.Client(client_id="manual_alarm_test")
    client.username_pw_set(user, pw)
    client.connect(broker, port)
    client.loop_start()

    print(f"[Manual] Publishing GPAP alarms to: {topic}")
    print("[Manual] Ctrl+C to stop\n")

    try:
        while True:
            desc = input("Alarm text: ").strip()
            sev = int(input("Severity (0-5): ").strip() or "0")
            mid = new_msg_id()

            msg = encode_gpap_alarm(sev, desc, msg_id=mid, max_len=80)
            client.publish(topic, msg, qos=1)
            print(f"Sent: {msg}\n")

    except KeyboardInterrupt:
        print("\n[Manual] Stopping...")
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()