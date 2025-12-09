import paho.mqtt.client as paho
import json
from datetime import datetime

BROKER = "broker.mqttdashboard.com"
ALARM_TOPIC = "PubInv-test973"
DEFAULT_ACK_TOPIC = "PubInv-test973/acks"

def on_subscribe(client, userdata, mid, granted_qos):
    print("Subscribed: ",mid, granted_qos)

def on_message(client, userdata, msg):
    print("n=== MESSAGE RECEIVED ===") 

    try:
        payload_text = msg.payload.decode("utf-8")
        payload = json.loads(payload_text)
    except json.JSONDecodeError:
        print("Not valid JSON:", msg.payload)
        return

    # Extract information from the alarm
    alarm_id = payload.get("alarm_id")
    level = payload.get("level")
    label = payload.get("label")
    description = payload.get("description")
    source = payload.get("source")

    print(f"Topic:       {msg.topic}")
    print(f"Alarm ID:    {alarm_id}")
    print(f"Level:       {level} ({label})")
    print(f"Description: {description}")
    print(f"Source:      {source}")

    # Figure out where to send the acknowledgement
    ack_topic = payload.get("ack_topic", DEFAULT_ACK_TOPIC)

    ack_payload = {
        "alarm_id": alarm_id,
        "status": "received",
        "received_at": datetime.utcnow().isoformat() + "Z",
    }

    client.publish(ack_topic, json.dumps(ack_payload), qos=1)
    print(f"ACK SENT → {ack_topic}")
    print("===========================\n")   

client = paho.Client()
client.on_subscribe = on_subscribe
client.on_message = on_message
client.connect('broker.mqttdashboard.com', 1883)
client.subscribe('PubInv-test973', qos=1)

client.loop_forever()
