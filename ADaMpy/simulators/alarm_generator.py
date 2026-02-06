import os
import json
import time
import random
import uuid
from datetime import datetime, timezone
from ADaMpy.gpad_api import (
    encode_gpad_alarm,
    decode_gpad_alarm,
    encode_gpad_ack,
    decode_gpad_ack,
)


import paho.mqtt.client as mqtt


CFG_FILE = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "config", "adam_config.json")
)

LEVELS = [1, 2, 3, 4, 5]


def load_cfg() -> dict:
    with open(CFG_FILE, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def main():
    cfg = load_cfg()
    topic = cfg.get("alarm_topic", "adam/in/alarms")

    client = mqtt.Client(
        client_id="alarm_generator",
        callback_api_version=mqtt.CallbackAPIVersion.VERSION1
    )
    client.username_pw_set(cfg.get("username", "public"), cfg.get("password", "public"))
    client.connect(cfg.get("broker_host", "public.cloud.shiftr.io"), int(cfg.get("broker_port", 1883)))
    client.loop_start()

    print(f"[Generator] Publishing alarms to: {topic}")
    print("[Generator] Ctrl+C to stop")

    try:
        while True:
            level = random.choice(LEVELS)
            payload = {
                "alarm_id": str(uuid.uuid4()),
                "severity": level,
                "label": ["", "Informational", "Problem", "Warning", "Critical", "Panic"][level],
                "description": "Simulated alarm",
                "source": "alarm-generator",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "state": "active",
            }

            # create string from payload which is a GPAD_API formatted string instead.
            # GPAD_API alarm payload (not JSON)
            # Format: a<severity><description up to 80 chars>
            desc = f"{payload['description']} id={payload['alarm_id'][:8]} src={payload['source']}"
            msg = encode_gpad_alarm(level, desc)
            info = client.publish(topic, msg, qos=1)

            if info.rc != 0:
                print(f"[Generator] Publish failed rc={info.rc}")
            else:
                print(f"[Generator] Sent alarm id={payload['alarm_id'][:8]} sev={level}")

            time.sleep(5)

    except KeyboardInterrupt:
        print("\n[Generator] Stopping...")
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
