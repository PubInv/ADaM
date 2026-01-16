import time
import random
import paho.mqtt.client as mqtt
from datetime import datetime, timezone
import json
import uuid
import os

BROKER = "public.cloud.shiftr.io"
PORT = 1883
TOPIC = "PubInv-test973"

USERNAME = os.getenv("MQTT_USER")
PASSWORD = os.getenv("MQTT_PASS")

LEVELS = [1, 2, 3, 4, 5]

client = mqtt.Client(client_id="AlarmGenerator")
client.username_pw_set(USERNAME, PASSWORD)
client.connect(BROKER, PORT)
client.loop_start()

print("[Generator] Started")

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
            "ack_topic": "PubInv-test973/acks",
        }

        client.publish(TOPIC, json.dumps(payload), qos=1)
        print(f"[Generator] Sent alarm severity={level}")

        time.sleep(5)

except KeyboardInterrupt:
    client.loop_stop()
    client.disconnect()
