import os
import json
import time
import random
import uuid
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

from ADaMpy.gpad_api import encode_gpap_alarm


CFG_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config", "adam_config.json"))

LEVELS = [1, 2, 3, 4, 5]
LABEL = ["", "Informational", "Problem", "Warning", "Critical", "Panic"]


def load_cfg() -> dict:
    with open(CFG_FILE, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def new_msg_id() -> str:
    return uuid.uuid4().hex[:5].upper()


def main():
    cfg = load_cfg()
    topic = cfg.get("alarm_topic", "adam/in/alarms")

    client = mqtt.Client(client_id="alarm_generator")
    client.username_pw_set(cfg.get("username", "public"), cfg.get("password", "public"))
    client.connect(cfg.get("broker_host", "public.cloud.shiftr.io"), int(cfg.get("broker_port", 1883)))
    client.loop_start()

    print(f"[Generator] Publishing GPAP alarms to: {topic}")
    print("[Generator] Ctrl+C to stop")

    try:
        while True:
            sev = random.choice(LEVELS)
            mid = new_msg_id()
            text = f"Simulated alarm [{LABEL[sev]}] src=alarm-generator at={datetime.now(timezone.utc).isoformat()}"

            msg = encode_gpap_alarm(sev, text, msg_id=mid, max_len=80)
            info = client.publish(topic, msg, qos=1)

            if info.rc != 0:
                print(f"[Generator] Publish failed rc={info.rc}")
            else:
                print(f"[Generator] Sent alarm msg_id={mid} sev={sev} payload={msg}")

            time.sleep(5)

    except KeyboardInterrupt:
        print("\n[Generator] Stopping...")
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()