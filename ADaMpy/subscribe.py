import json
import os
import threading
from datetime import datetime, timezone
import paho.mqtt.client as mqtt

BROKER = "public.cloud.shiftr.io"
PORT = 1883
USERNAME = "public"
PASSWORD = "public"

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config", "adam_config.json")

lock = threading.Lock()
alarms: list[dict] = []
client = None

SUB_TOPIC = None
ACK_TOPIC = None
POLICY = "POLICY0"


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def severity_sort_key(a: dict):
    sev = int(a.get("severity", 0))
    ts = a.get("timestamp") or a.get("received_at") or ""
    seq = int(a.get("seq", 0))
    return (-sev, ts, seq)


def get_active_view():
    """
    Returns a list of tuples: (display_index_1_based, alarm_index_in_master_list, alarm_dict)
    Display order depends on POLICY.
    """
    with lock:
        active_items = [(idx, a) for idx, a in enumerate(alarms) if a.get("status") == "active"]

    if POLICY == "SEVERITY":
        active_items.sort(key=lambda x: severity_sort_key(x[1]))
    else:
        # POLICY0: arrival order
        active_items.sort(key=lambda x: x[1].get("seq", 0))

    # Build display list
    view = []
    for display_i, (master_idx, alarm) in enumerate(active_items, 1):
        view.append((display_i, master_idx, alarm))
    return view


def get_all_view():
    """
    Returns list of (display_index_1_based, master_idx, alarm_dict) ordered by POLICY.
    """
    with lock:
        items = list(enumerate(alarms))  # (master_idx, alarm)

    if POLICY == "SEVERITY":
        items.sort(key=lambda x: severity_sort_key(x[1]))
    else:
        items.sort(key=lambda x: x[1].get("seq", 0))

    view = []
    for display_i, (master_idx, alarm) in enumerate(items, 1):
        view.append((display_i, master_idx, alarm))
    return view


def print_view(view):
    print("\n--- Alarms ---")
    for display_i, _, a in view:
        print(
            f"{display_i}) [{a.get('status')}] "
            f"sev={a.get('severity')} "
            f"desc={a.get('description')} "
            f"id={a.get('alarm_id')}"
        )
    print("-------------\n")


def send_ack(alarm_id: str, status: str):
    payload = {
        "alarm_id": alarm_id,
        "status": status,
        "ack_at": utc_now()
    }
    client.publish(ACK_TOPIC, json.dumps(payload), qos=1)
    print(f"[Krake] ACK sent → alarm_id={alarm_id} status={status}")


def acknowledge(display_n: int):
    """
    POLICY0: allow acknowledging any active alarm number in the ACTIVE view
    SEVERITY: must acknowledge the top alarm first => display_n must be 1
    """
    active_view = get_active_view()

    if not active_view:
        print("No active alarms")
        return

    if POLICY == "SEVERITY" and display_n != 1:
        print("Must acknowledge from the top of the list (A-1 first)")
        return

    match = None
    for display_i, master_idx, alarm in active_view:
        if display_i == display_n:
            match = (master_idx, alarm)
            break

    if not match:
        print("Invalid alarm number for ACTIVE list")
        return

    master_idx, alarm = match
    alarm_id = alarm.get("alarm_id")

    with lock:
        alarms[master_idx]["status"] = "acknowledged"

    send_ack(alarm_id, "acknowledged")
    print(f"[Krake] Alarm acknowledged → alarm_id={alarm_id}")


def on_connect(_client, _userdata, _flags, rc):
    print("[Krake] Connected to broker")
    _client.subscribe(SUB_TOPIC, qos=1)
    print(f"[Krake] Subscribed to {SUB_TOPIC}")

    print("\nCommands:")
    print(" list           -> show ACTIVE alarms (ordered by policy)")
    print(" list all       -> show ALL alarms (ordered by policy)")
    print(" A-<n>          -> acknowledge alarm #n (POLICY0: any, SEVERITY: only A-1)")
    print(" exit\n")


def on_message(_client, _userdata, msg):
    alarm = json.loads(msg.payload.decode("utf-8"))

    alarm_id = alarm.get("alarm_id")
    severity = alarm.get("severity")
    label = alarm.get("label")
    source = alarm.get("source")

    with lock:
        seq = len(alarms) + 1
        alarms.append({
            "seq": seq,
            "alarm_id": alarm_id,
            "severity": severity,
            "description": alarm.get("description"),
            "timestamp": alarm.get("timestamp"),
            "label": label,
            "source": source,
            "status": "active",
            "received_at": utc_now()
        })

    print(
        f"[Krake] Alarm received → "
        f"id={alarm_id}, "
        f"severity={severity}, "
        f"label={label}, "
        f"source={source}"
    )

    # Always ACK as "received" immediately (your requirement)
    send_ack(alarm_id, "received")


def command_loop():
    while True:
        cmd = input("> ").strip()

        if cmd == "list":
            print_view(get_active_view())
        elif cmd == "list all":
            print_view(get_all_view())
        elif cmd.upper().startswith("A-"):
            try:
                n = int(cmd.split("-", 1)[1])
                acknowledge(n)
            except ValueError:
                print("Invalid command format. Use A-1, A-2, etc.")
        elif cmd == "exit":
            break
        else:
            print("Unknown command. Try: list, list all, A-1, exit")


def main():
    global client, SUB_TOPIC, ACK_TOPIC, POLICY

    config = load_config(CONFIG_PATH)
    POLICY = config.get("policy", "POLICY0").upper()
    ACK_TOPIC = config.get("ack_topic", "adam/acks")

    annunciators = config.get("annunciators", [])
    if not annunciators:
        raise RuntimeError("No annunciators found in config")
    SUB_TOPIC = annunciators[0]

    print(f"[Krake] Policy: {POLICY}")
    print(f"[Krake] SUB_TOPIC: {SUB_TOPIC}")
    print(f"[Krake] ACK_TOPIC: {ACK_TOPIC}")

    client = mqtt.Client(
        client_id="KrakeSimulator",
        callback_api_version=mqtt.CallbackAPIVersion.VERSION1
    )
    client.username_pw_set(USERNAME, PASSWORD)
    client.on_connect = on_connect
    client.on_message = on_message

    print("[Krake] Connecting to broker...")
    client.connect(BROKER, PORT)
    client.loop_start()

    command_loop()


if __name__ == "__main__":
    main()
