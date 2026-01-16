import paho.mqtt.client as paho
import json
import threading
from datetime import datetime, timezone, timedelta

BROKER = "broker.mqttdashboard.com"
ALARM_TOPIC = "PubInv-test973/krake"
DEFAULT_ACK_TOPIC = "PubInv-test973/acks"
LOG_FILE = "alarm_log.jsonl"

# Simulator policy: alarms with level >= this will beep (unless muted)
BEEP_LEVEL_THRESHOLD = 4

alarms = []
alarms_lock = threading.Lock()


def utc_now_dt():
    return datetime.now(timezone.utc)


def utc_now_str():
    return utc_now_dt().isoformat()


def append_jsonl(entry: dict) -> None:
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def rewrite_jsonl(all_entries: list[dict]) -> None:
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        for e in all_entries:
            f.write(json.dumps(e) + "\n")


def is_muted(alarm: dict) -> bool:
    muted_until = alarm.get("muted_until")
    if not muted_until:
        return False
    try:
        # muted_until stored as ISO string
        until_dt = datetime.fromisoformat(muted_until)
        return utc_now_dt() < until_dt
    except ValueError:
        # if parsing fails, treat as not muted
        return False


def try_beep():
    # Windows beep if available; otherwise print
    try:
        import winsound
        winsound.Beep(1000, 250)  # frequency, duration(ms)
    except Exception:
        print("BEEP!")


def print_alarm(a: dict, idx: int):
    muted = is_muted(a)
    muted_text = "muted" if muted else "not-muted"
    print(
        f"{idx}) [{a.get('status')}] "
        f"lvl={a.get('level')} "
        f"{muted_text} "
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
        alarm[f"{new_status}_at"] = utc_now_str()

        # If acknowledging or dismissing, clear mute fields (optional)
        if new_status in ("acknowledged", "dismissed"):
            alarm.pop("muted_until", None)
            alarm.pop("muted_at", None)

        rewrite_jsonl(alarms)

    print(f"{new_status.upper()} alarm #{index_1_based} (alarm_id={alarm.get('alarm_id')})")


def mute_alarm(index_1_based: int, seconds: int):
    with alarms_lock:
        if index_1_based < 1 or index_1_based > len(alarms):
            print(f"Invalid alarm number: {index_1_based}")
            return

        alarm = alarms[index_1_based - 1]
        if alarm.get("status") != "active":
            print("You can only mute ACTIVE alarms.")
            return

        until_dt = utc_now_dt() + timedelta(seconds=seconds)
        alarm["muted_at"] = utc_now_str()
        alarm["muted_until"] = until_dt.isoformat()

        rewrite_jsonl(alarms)

    print(f"Muted alarm #{index_1_based} for {seconds}s (until {until_dt.isoformat()})")


def unmute_alarm(index_1_based: int):
    with alarms_lock:
        if index_1_based < 1 or index_1_based > len(alarms):
            print(f"Invalid alarm number: {index_1_based}")
            return

        alarm = alarms[index_1_based - 1]
        alarm.pop("muted_until", None)
        alarm.pop("muted_at", None)

        rewrite_jsonl(alarms)

    print(f"Unmuted alarm #{index_1_based}")


def command_loop():
    print("\nCommands:")
    print("  list           -> show ACTIVE alarms")
    print("  list all       -> show all alarms")
    print("  A-<n>          -> acknowledge/complete alarm #n (example: A-2)")
    print("  D-<n>          -> dismiss alarm #n (example: D-2)")
    print("  M-<n> <sec>    -> mute alarm #n for seconds (example: M-2 30)")
    print("  unmute-<n>     -> unmute alarm #n")
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

        if cmd.upper().startswith("D-"):
            try:
                n = int(cmd.split("-", 1)[1])
            except ValueError:
                print("Invalid format. Use D-2, D-3, etc.")
                continue
            set_status(n, "dismissed")
            continue

        if cmd.upper().startswith("M-"):
            parts = cmd.split()
            if len(parts) != 2:
                print("Use: M-<n> <seconds>   example: M-2 30")
                continue
            try:
                n = int(parts[0].split("-", 1)[1])
                sec = int(parts[1])
            except ValueError:
                print("Use: M-<n> <seconds>   example: M-2 30")
                continue
            if sec <= 0:
                print("Seconds must be > 0")
                continue
            mute_alarm(n, sec)
            continue

        if cmd.lower().startswith("unmute-"):
            try:
                n = int(cmd.split("-", 1)[1])
            except ValueError:
                print("Use unmute-<n> like unmute-2")
                continue
            unmute_alarm(n)
            continue

        print("Unknown command. Try: list, list all, A-1, D-1, M-1 60, unmute-1, exit")


def on_connect(client, userdata, flags, rc):
    print("Connected to broker, rc =", rc)
    client.subscribe(ALARM_TOPIC, qos=1)
    print("Subscribed to:", ALARM_TOPIC)


def on_subscribe(client, userdata, mid, granted_qos):
    print("Subscribed:", mid, granted_qos)


def on_message(client, userdata, msg):
    try:
        payload_text = msg.payload.decode("utf-8")
        payload = json.loads(payload_text)
    except json.JSONDecodeError:
        print("Not valid JSON:", msg.payload)
        return

    alarm_id = payload.get("alarm_id")
    level = payload.get("level")
    label = payload.get("label")
    description = payload.get("description")
    source = payload.get("source")

    log_entry = {
        "alarm_id": alarm_id,
        "level": level,
        "label": label,
        "description": description,
        "source": source,
        "topic": msg.topic,
        "received_at": utc_now_str(),
        "status": "active",
    }

    with alarms_lock:
        alarms.append(log_entry)
        alarm_number = len(alarms)

    append_jsonl(log_entry)

    # Simulator behavior: beep if high severity and not muted
    print(f"\n=== ALARM #{alarm_number} RECEIVED ===")
    print(f"Level: {level} ({label}) | Desc: {description} | Source: {source}")

    try:
        lvl_int = int(level) if level is not None else 0
    except ValueError:
        lvl_int = 0

    if lvl_int >= BEEP_LEVEL_THRESHOLD and not is_muted(log_entry):
        try_beep()

    # Send ACK back to publisher (still useful for testing)
    ack_topic = payload.get("ack_topic", DEFAULT_ACK_TOPIC)
    ack_payload = {
        "topic_id": msg.topic,
        "message": "Alarm received",
        "alarm_id": alarm_id,
        "status": "received",
        "received_at": utc_now_str(),  # <-- fixed: must call function
    }
    result = client.publish(ack_topic, json.dumps(ack_payload), qos=1)
    print(f"Sent ACK to {ack_topic} | topic_id={msg.topic}")


def main():
    client = paho.Client(client_id="AlarmSimulator")
    client.on_connect = on_connect
    client.on_subscribe = on_subscribe
    client.on_message = on_message

    print("Connecting to broker...")
    client.connect(BROKER, 1883, keepalive=60)

    # Run MQTT networking in background so the simulator can accept commands
    client.loop_start()
    try:
        command_loop()
    finally:
        client.loop_stop()
        client.disconnect()
        print("Disconnected.")


if __name__ == "__main__":
    main()
