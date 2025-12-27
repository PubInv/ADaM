import paho.mqtt.client as paho
import json
from datetime import datetime, timezone
import logging
from logging.handlers import RotatingFileHandler
import threading

BROKER = "broker.mqttdashboard.com"
ALARM_TOPIC = "PubInv-test973"
DEFAULT_ACK_TOPIC = "PubInv-test973/acks"

LOG_FILE = "alarm_log.jsonl"

alarms = []
alarms_lock = threading.Lock()

#logger = logging.getLogger("alarm")
#logger.setLevel(logging.INFO)


# handler = RotatingFileHandler(LOG_FILE, maxBytes= 1_000_000, backupCount=3, encoding="utf-8")
# formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
# handler.setFormatter(formatter)

# if not logger.handlers:
#     logger.addHandler(handler)

def utc_now():
    return datetime.now(timezone.utc).isoformat()

def append_jsonl(entry:dict)-> None:
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

def rewrite_jsonl(all_entries: list[dict])-> None:

    with open(LOG_FILE, "w", encoding="utf-8") as f:
        for e in all_entries:
            f.write(json.dumps(e) + "\n")

def print_alarm_list():
    for i, a in enumerate(alarms, start=1):
        print(
            f"{i}) [{a.get('status')}] "
            f"lvl={a.get('level')} "
            f"desc={a.get('description')} "
            f"src={a.get('source')} "
            f"id={a.get('alarm_id')}"
        )
    print("-------\n")

# def dismiss_alarm(index_1_based: int):
#     with alarms_lock:
#         if index_1_based < 1 or index_1_based > len(alarms):
#             print(f"invalid alarm number: {index_1_based}")
#             return
        
#         alarm = alarms[index_1_based -1]
#         if alarm.get("status") == "dismissed":
#             print(f"alarm #{index_1_based} is alread dismissed.")
#             return
        
#         alarm["status"] = "dismissed"
#         alarm["dismissed_at"] = utc_now()

#         rewrite_jsonl(alarms)

#     print(f"Dismissed alarm #{index_1_based} (alarm_id={alarm.get('alarm_id')})")

def command_loop():
    print("\nCommands:")
    print("  list       -> show alarms")
    print("  D-<n>      -> dismiss alarm #n (example: D-2)")
    print("  exit       -> quit\n")

    while True:
        cmd = input("> ").strip()

        if cmd.lower() == "exit":
            break
        if cmd.lower() == "list":
            print_alarm_list()
            continue

        if cmd.upper().startswith("D-"):
            try:
                n = int(cmd.split("-",1)[1])
                dismiss_alarm(n)
            except ValueError:
                print("Invalid format. use D-2, D-3, etc...")
            continue

        print("Unknown command. Try: list, D-1, exit")

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
        "received_at": utc_now(),
        "status": "active",
    }

    with alarms_lock:
        alarms.append(log_entry)
        alarm_number = len(alarms)

    append_jsonl(log_entry)
    print(f"Saved alarm #{alarm_number} (status=active)")
    

    # try:
    #     with open(LOG_FILE, "a", encoding="utf-8") as f:
    #         f.write(json.dumps(log_entry) + "\n")
    # except Exception as e:
    #     print("Failed to write to log file",e)

    # Figure out where to send the acknowledgement
    ack_topic = payload.get("ack_topic", DEFAULT_ACK_TOPIC)

    ack_payload = {
        "alarm_id": alarm_id,
        "status": "received",
        "received_at": utc_now
    }

    client.publish(ack_topic, json.dumps(ack_payload), qos=1)
    print(f"ACK SENT → {ack_topic}")
    print("===========================\n")   

def main():
    client = paho.Client(client_id="AlarmSubscriber")
    client.on_connect = on_connect
    client.on_subscribe = on_subscribe
    client.on_message = on_message

    print("connecting to broker...")
    #logger.info(f"CONNECTING | broker={BROKER} | port=1883")
    client.connect(BROKER, 1883, keepalive=60)
    #logger.info(f"SUBSCRIBE_REQUEST | topic={ALARM_TOPIC} | qos=1")
    #client.loop_forever()

    client.loop_start()
    try:
        command_loop()
    finally:
        client.loop_stop()
        client.disconnect()
        print("disconnected")


if __name__ == "__main__":
    main()