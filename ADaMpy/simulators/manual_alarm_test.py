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
    desc = input("Alarm description (max 80 chars): ").strip()

    # limit to 80 chars
    if len(desc) > 80:
        print("Description too long (max 80 characters).")
        continue

    # severity input
    try:
        sev = int(input("Severity (1-5): "))
        if sev < 1 or sev > 5:
            print("Severity must be between 1 and 5.")
            continue
    except ValueError:
        print("Enter a valid number 1-5.")
        continue

    
    payload_text = f"{sev}-{desc}"

    client.publish(TOPIC, payload_text, qos=1)

    print(f"Alarm sent: {payload_text}\n")
