import os
import json
from datetime import datetime

import paho.mqtt.client as mqtt


CFG_PATH = os.path.join("ADaMpy", "config", "adam_config.json")


def now():
    return datetime.now().strftime("%H:%M:%S")


def load_cfg():
    with open(CFG_PATH, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def classify(payload: str) -> str:
    s = (payload or "").lstrip()
    if not s:
        return "EMPTY"
    if s.startswith("{"):
        return "JSON"
    if s.startswith("a") and len(s) >= 2 and s[1].isdigit():
        return "GPAD_ALARM"
    if s.startswith("k|") or s.startswith("k,") or s.startswith("k "):
        return "GPAD_ACK"
    return "UNKNOWN"


def on_connect(client, userdata, flags, rc):
    print(f"[{now()}] CONNECT rc={rc}")
    for t in userdata["topics"]:
        client.subscribe(t, qos=1)
        print(f"[{now()}] SUB {t}")


def on_message(client, userdata, msg):
    raw = msg.payload.decode("utf-8", errors="replace")
    kind = classify(raw)
    preview = raw.replace("\r", "\\r").replace("\n", "\\n")
    if len(preview) > 200:
        preview = preview[:200] + "..."

    print(f"[{now()}] {kind} topic={msg.topic} payload={preview}")


def main():
    cfg = load_cfg()

    broker = cfg.get("broker_host", "public.cloud.shiftr.io")
    port = int(cfg.get("broker_port", 1883))
    user = cfg.get("username", "public")
    pw = cfg.get("password", "public")

    alarm_topic = cfg.get("alarm_topic", "adam/in/alarms")
    ack_topic = cfg.get("ack_topic", "adam/acks")
    annunciators = list(cfg.get("annunciators", []))

    topics = [alarm_topic, ack_topic] + annunciators

    client = mqtt.Client(client_id="sniff_mqtt")
    client.username_pw_set(user, pw)

    client.user_data_set({"topics": topics})
    client.on_connect = on_connect
    client.on_message = on_message

    print(f"[{now()}] Connecting to {broker}:{port}")
    print(f"[{now()}] Watching topics:")
    for t in topics:
        print("  -", t)

    client.connect(broker, port)
    client.loop_forever()


if __name__ == "__main__":
    main()
