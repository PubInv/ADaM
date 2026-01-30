import paho.mqtt.client as paho
from datetime import datetime, timezone
import json
import threading

BROKER = "public.cloud.shiftr.io"
ALARM_TOPIC = "PubInv-test973"
ACK_TOPIC = "PubInv-test973/acks"   

lock = threading.Lock()

receieved_Alarm = ""       
ack_Text = ""      
received_At = ""     


def now_utc_str():
    return datetime.now(timezone.utc).isoformat()


def on_connect(client, userdata, flags, rc):
    print("Connected, rc =", rc)
    client.subscribe(ALARM_TOPIC, qos=1)
    print("Subscribed to:", ALARM_TOPIC) 


def on_message(client, userdata, msg):
    global receieved_Alarm, ack_

    payload_bytes = msg.payload
    received_at = now_utc_str()

    desc = ""
    try:
        payload_text = payload_bytes.decode("utf-8", errors="replace")
        data = json.loads(payload_text)
        desc = data.get("description") or "(no description)"
    except Exception:
        desc = payload_bytes.decode("utf-8", errors="replace")

    with lock:
        ack_Text = d = received_at
        receieved_Alarm = f"[{received_at}] {desc}"

    print("\nNEW ALARM RECEIVED")
    print(receieved_Alarm)
    print("Type 'ack' to acknowledge.\n")


def command_loop(client: paho.Client):
    global receieved_Alarm, ack_

    print("\nKrakeSimulator running.")
    print("Commands:")
    print("  ack  -> acknowledge latest alarm (sends plain-text ACK)")
    print("  show -> show latest alarm")
    print("  exit -> quit\n")

    while True:
        cmd = input("> ").strip().lower()

        if cmd == "exit":
            break

        if cmd == "show":
            with lock:
                if receieved_Alarm:
                    print(receieved_Alarm)
                else:
                    print("(no alarm yet)")
            continue

        if cmd == "ack":
            with lock:
                if not ack_Text:
                    print("No alarm to acknowledge yet.")
                    continue

                # ACK payload in plain text: description + timestamp only
                ack_Text = f"{received_At} | {ack_Text}"


            client.publish(ACK_TOPIC, ack_Text, qos=1)
            print("ACK SENT ->", ACK_TOPIC)
            continue

        print("Unknown command. Try: ack, show, exit")


def main():
    client = paho.Client(client_id="KrakeSimulator")
    client.on_connect = on_connect
    client.on_message = on_message

    print("Connecting to broker...")
    client.connect(BROKER, 1883, keepalive=60)

    # MQTT loop in background so we can still use input()
    client.loop_start()
    try:
        command_loop(client)
    finally:
        client.loop_stop()
        client.disconnect()
        print("Disconnected.")


if __name__ == "__main__":
    main()