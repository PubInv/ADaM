from enum import IntEnum
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import uuid
import os
import paho.mqtt.client as mqtt


# =========================
# Alarm Severity Definition
# =========================

class AlarmLevel(IntEnum):
    INFORMATIONAL = 1
    PROBLEM = 2
    WARNING = 3
    CRITICAL = 4
    PANIC = 5


ALARM_LABELS = {
    AlarmLevel.INFORMATIONAL: "Informational",
    AlarmLevel.PROBLEM: "Problem",
    AlarmLevel.WARNING: "Warning",
    AlarmLevel.CRITICAL: "Critical",
    AlarmLevel.PANIC: "Panic",
}


# =========================
# Alarm Model
# =========================

@dataclass
class Alarm:
    alarm_id: str
    level: AlarmLevel
    description: str | None
    source: str
    timestamp: str
    state: str = "active"


# =========================
# Encoding
# =========================

def encode_alarm(alarm: Alarm, ack_topic: str | None = None) -> str:
    payload = {
        "alarm_id": alarm.alarm_id,
        "severity": int(alarm.level),
        "label": ALARM_LABELS[alarm.level],
        "description": alarm.description,
        "source": alarm.source,
        "timestamp": alarm.timestamp,
        "state": alarm.state,
    }

    if ack_topic:
        payload["ack_topic"] = ack_topic

    return json.dumps(payload)


# =========================
# ADaM Server
# =========================

class ADaMServer:
    def __init__(
        self,
        broker_host: str,
        broker_port: int,
        alarm_topic: str,
        ack_topic: str,
        client_id: str = "ADaMServer",
        username: str | None = None,
        password: str | None = None,
    ):
        self.alarm_topic = alarm_topic
        self.ack_topic = ack_topic

        self.client = mqtt.Client(client_id=client_id)

        if username and password:
            self.client.username_pw_set(username, password)

        # Unified message handler
        self.client.on_message = self.on_message

        self.client.connect(broker_host, broker_port)
        self.client.subscribe(self.alarm_topic, qos=1)
        self.client.subscribe(self.ack_topic, qos=1)

        self.client.loop_start()

        print("[ADaM] Server started")
        print(f"[ADaM] Broker: {broker_host}:{broker_port}")
        print(f"[ADaM] Alarm topic: {self.alarm_topic}")
        print(f"[ADaM] ACK topic:   {self.ack_topic}")

    # ---------- MQTT Routing ----------

    def on_message(self, client, userdata, msg):
        payload = msg.payload.decode("utf-8")

        if msg.topic == self.alarm_topic:
            self.handle_alarm(payload)
        elif msg.topic == self.ack_topic:
            self.handle_ack(payload)
        else:
            print(f"[ADaM] Unknown topic received: {msg.topic}")

    # ---------- Alarm Intake ----------

    def handle_alarm(self, payload: str):
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            print("[ADaM] Invalid alarm JSON received")
            return

        alarm_id = data.get("alarm_id")
        severity = data.get("severity")
        label = data.get("label")

        print(
            f"[ADaM] Alarm received → "
            f"id={alarm_id}, severity={severity}, label={label}"
        )

        # NOTE:
        # No forwarding yet.
        # No policy yet.
        # This is intake verification only.

    # ---------- ACK Handling ----------

    def handle_ack(self, payload: str):
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            print("[ADaM] Invalid ACK payload received")
            return

        alarm_id = data.get("alarm_id")
        status = data.get("status")

        print(f"[ADaM] ACK received → alarm_id={alarm_id}, status={status}")

    # ---------- Shutdown ----------

    def stop(self):
        self.client.loop_stop()
        self.client.disconnect()
        print("[ADaM] Server stopped")


# =========================
# Main Entry Point
# =========================

def main():
    server = ADaMServer(
        broker_host="public.cloud.shiftr.io",
        broker_port=1883,
        alarm_topic="PubInv-test973",
        ack_topic="PubInv-test973/acks",
        username=os.getenv("MQTT_USER"),
        password=os.getenv("MQTT_PASS"),
    )

    try:
        while True:
            pass
    except KeyboardInterrupt:
        print("\n[ADaM] Shutting down")
        server.stop()


if __name__ == "__main__":
    main()
