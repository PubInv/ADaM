import json
import uuid
from datetime import datetime, timezone
import paho.mqtt.client as mqtt

BROKER = "public.cloud.shiftr.io"
PORT = 1883
TOPIC = "adam/in/alarms"

client = mqtt.Client(
    client_id="ManualAlarmTest",
    callback_api_version=mqtt.CallbackAPIVersion.VERSION1
)
client.username_pw_set("public", "public")
client.connect(BROKER, PORT)
client.loop_start()

while True:
    desc = input("Alarm description: ")
    sev = int(input("Severity (1-5): "))

    payload = {
        "alarm_id": str(uuid.uuid4()),
        "severity": sev,
        "description": desc,
        "source": "manual-test",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    client.publish(TOPIC, json.dumps(payload), qos=1)
    print("Alarm sent\n")
