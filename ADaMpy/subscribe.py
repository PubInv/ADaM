import json
import threading
from datetime import datetime, timezone
import paho.mqtt.client as mqtt

# =========================
# MQTT CONFIG (MUST MATCH ADaM)
# =========================

BROKER = "public.cloud.shiftr.io"
PORT = 1883
USERNAME = "public"
PASSWORD = "public"

ALARM_TOPIC = "adam/out/LEBANON-5"          # MUST match ADaM publish topic
DEFAULT_ACK_TOPIC = "adam/acks"

BEEP_LEVEL_THRESHOLD = 4

alarms = []
alarms_lock = threading.Lock()

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


def print_alarm(a: dict, idx: int):
    
    print(
        f"{idx}) [{a.get('status')}] "
        f"lvl={a.get('level')} "
        f"desc={a.get('description')} "
        f"src={a.get('source')} "
        f"id={a.get('alarm_id')}"
    )


def print_alarm_list(show_all: bool = False):
    with alarms_lock:
        if not alarms:
            print("\nNo alarms yet.\n")
            return

        print("\n--- Alarms ---")
        for i, a in enumerate(alarms, start=1):
            if not show_all and a.get("status") != "active":
                continue
            print_alarm(a, i)
        print("-------------\n")


def set_status(index_1_based: int, new_status: str):
    with alarms_lock:
        if index_1_based < 1 or index_1_based > len(alarms):
            print(f"Invalid alarm number: {index_1_based}")
            return

        alarm = alarms[index_1_based - 1]
        alarm["status"] = new_status
        alarm[f"{new_status}_at"] = utc_now()

        # If acknowledging or dismissing, clear mute fields (optional)
        if new_status in ("acknowledged", "dismissed"):
            alarm.pop("muted_until", None)
            alarm.pop("muted_at", None)

        rewrite_jsonl(alarms)

    print(f"{new_status.upper()} alarm #{index_1_based} (alarm_id={alarm.get('alarm_id')})")

def command_loop():
    print("\nCommands:")
    print("  list           -> show ACTIVE alarms")
    print("  list all       -> show all alarms")
    print("  A-<n>          -> acknowledge/complete alarm #n (example: A-2)")
    print("  exit           -> quit\n")

    while True:
        cmd = input("> ").strip()

        if cmd.lower() == "exit":
            break

        if cmd.lower() == "list":
            print_alarm_list(show_all=False)
            continue

        if cmd.lower() == "list all":
            print_alarm_list(show_all=True)
            continue

        if cmd.upper().startswith("A-"):
            try:
                n = int(cmd.split("-", 1)[1])
            except ValueError:
                print("Invalid format. Use A-2, A-3, etc.")
                continue
            set_status(n, "acknowledged")
            continue

       

        print("Unknown command. Try: list, list all, A-1, D-1, M-1 60, unmute-1, exit")

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
    timestamp = payload.get("timestamp")

    log_entry = {
        "alarm_id": alarm_id,
        "severity": severity,
        "label": label,
        "description": description,
        "source": source,
        "topic": msg.topic,
        "received_at": utc_now(),
        "status": "active",
    }

    with alarms_lock:
        alarms.append(log_entry)
        alarm_number = len(alarms)

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
