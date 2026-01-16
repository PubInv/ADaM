import json
from datetime import datetime, timezone
import paho.mqtt.client as mqtt

# =========================
# MQTT CONFIG (MUST MATCH ADaM)
# =========================

BROKER = "public.cloud.shiftr.io"
PORT = 1883
USERNAME = "public"
PASSWORD = "public"

ALARM_TOPIC = "PubInv-test973"          # MUST match ADaM publish topic
DEFAULT_ACK_TOPIC = "PubInv-test973/acks"

BEEP_LEVEL_THRESHOLD = 4


# =========================
# HELPERS
# =========================

def utc_now():
    return datetime.now(timezone.utc).isoformat()


def try_beep():
    try:
        import winsound
        winsound.Beep(1000, 300)
    except Exception:
        print("[Krake] BEEP")


# =========================
# MQTT CALLBACKS
# =========================

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("[Krake] Connected to broker")
        client.subscribe(ALARM_TOPIC, qos=1)
        print(f"[Krake] Subscribed to {ALARM_TOPIC}")
    else:
        print("[Krake] Connection failed, rc =", rc)


def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode("utf-8"))
    except json.JSONDecodeError:
        print("[Krake] Invalid JSON received")
        return

    alarm_id = payload.get("alarm_id")
    severity = payload.get("severity")
    label = payload.get("label")
    description = payload.get("description")
    source = payload.get("source")

    print(
        f"[Krake] Alarm received → "
        f"id={alarm_id}, severity={severity}, label={label}, source={source}"
    )

    # Simulate hardware reaction
    try:
        sev_int = int(severity)
    except (TypeError, ValueError):
        sev_int = 0

    if sev_int >= BEEP_LEVEL_THRESHOLD:
        try_beep()

    # Send ACK back to ADaM
    ack_topic = payload.get("ack_topic", DEFAULT_ACK_TOPIC)
    ack_payload = {
        "alarm_id": alarm_id,
        "status": "received",
        "ack_at": utc_now(),
    }

    client.publish(ack_topic, json.dumps(ack_payload), qos=1)
    print(f"[Krake] ACK sent → alarm_id={alarm_id}")


# =========================
# MAIN
# =========================

def main():
    client = mqtt.Client(client_id="KrakeSimulator")
    client.username_pw_set(USERNAME, PASSWORD)

    client.on_connect = on_connect
    client.on_message = on_message

    print("[Krake] Connecting to broker...")
    client.connect(BROKER, PORT, keepalive=60)

    client.loop_forever()


if __name__ == "__main__":
    main()
