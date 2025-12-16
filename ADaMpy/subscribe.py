import paho.mqtt.client as paho
import json
from datetime import datetime
import logging
from logging.handlers import RotatingFileHandler

BROKER = "broker.mqttdashboard.com"
ALARM_TOPIC = "PubInv-test973"
DEFAULT_ACK_TOPIC = "PubInv-test973/acks"

LOG_FILE = "alarm_log.jsonl"

logger = logging.getLogger("alarm")
logger.setLevel(logging.INFO)


handler = RotatingFileHandler(LOG_FILE, maxBytes= 1_000_000, backupCount=3, encoding="utf-8")
formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
handler.setFormatter(formatter)

if not logger.handlers:
    logger.addHandler(handler)

def on_connect(client, userdata, flags, rc):
    print("connected to broker, rc", rc)
    client.subscribe(ALARM_TOPIC, qos=1)
    print("Subscribed to:", ALARM_TOPIC)

def on_subscribe(client, userdata, mid, granted_qos):
    print("Subscribed: ",mid, granted_qos)

def on_message(client, userdata, msg):
    print("\n=== MESSAGE RECEIVED ===") 

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

    log_entry = {
        "alarm_id": alarm_id,
        "level": level,
        "label": label,
        "description": description,
        "source": source,
        "topic": msg.topic,
        "received_at": datetime.utcnow().isoformat() + "Z",
    }
    

    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")
    except Exception as e:
        print("Failed to write to log file",e)

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

client = paho.Client(client_id="AlarmSubscriber")
client.on_connect = on_connect
client.on_subscribe = on_subscribe
client.on_message = on_message

print("connecting to broker...")
logger.info(f"CONNECTING | broker={BROKER} | port=1883")
client.connect(BROKER, 1883, keepalive=60)


logger.info(f"SUBSCRIBE_REQUEST | topic={ALARM_TOPIC} | qos=1")

client.loop_forever()
