import os
import json
import time
import random
import uuid
from datetime import datetime, timezone

import paho.mqtt.client as mqtt


CFG_FILE = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "config", "adam_config.json")
)

LEVELS = [1, 2, 3, 4, 5]


def load_cfg(path: str) -> dict:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Config not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    cfg = load_cfg(CFG_FILE)

    broker = cfg["broker_host"]
    port = int(cfg["broker_port"])
    username = cfg.get("username", "")
    password = cfg.get("password", "")
    topic = cfg["alarm_topic"]  # ADaMServer must subscribe to this

    client = mqtt.Client(client_id="AlarmGenerator")
    if username:
        client.username_pw_set(username, password)

    client.connect(broker, port)
    client.loop_start()

    print(f"[Generator] Using config: {CFG_FILE}")
    print(f"[Generator] Connected broker={broker}:{port}")
    print(f"[Generator] Publishing to alarm_topic={topic}")

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
            msg = json.dumps(payload)
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
