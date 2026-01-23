from enum import IntEnum
from datetime import datetime, timezone
import json
import os
import paho.mqtt.client as mqtt

# ============================================================
# Rob / Forrest reference code — DO NOT TOUCH (KEEP COMMENTED)
# ============================================================

# `mac_to_NameDict.set("F4650BC0B52C", "KRAKE_US0006");
# // Make MAC to Serial number association in this dictionary
# StringDict mac_to_NameDict = new StringDict();
# void setupDictionary() {
#
#   mac_to_NameDict.set("F024F9F1B874", "KRAKE_LB0001");
#   mac_to_NameDict.set("142B2FEB1F00", "KRAKE_LB0002");
#   mac_to_NameDict.set("142B2FEB1C64", "KRAKE_LB0003");
#   mac_to_NameDict.set("142B2FEB1E24", "KRAKE_LB0004");
#   mac_to_NameDict.set("F024F9F1B880", "KRAKE_LB0005");
#
#   mac_to_NameDict.set("F4650BC0B52C", "KRAKE_US0006");
#   mac_to_NameDict.set("ECC9FF7D8EE8", "KRAKE_US0005");
#   mac_to_NameDict.set("ECC9FF7D8EF4", "KRAKE_US0004");
#   mac_to_NameDict.set("ECC9FF7C8C98", "KRAKE_US0003");
#   mac_to_NameDict.set("ECC9FF7D8F00", "KRAKE_US0002");
#   mac_to_NameDict.set("ECC9FF7C8BDC", "KRAKE_US0001");
#   mac_to_NameDict.set("3C61053DF08C", "20240421_USA1");
#   mac_to_NameDict.set("3C6105324EAC", "20240421_USA2");
#   mac_to_NameDict.set("3C61053DF63C", "20240421_USA3");
#   mac_to_NameDict.set("10061C686A14", "20240421_USA4");
#   mac_to_NameDict.set("FCB467F4F74C", "20240421_USA5");
#   mac_to_NameDict.set("CCDBA730098C", "20240421_LEB1");
#   mac_to_NameDict.set("CCDBA730BFD4", "20240421_LEB2");
#   mac_to_NameDict.set("CCDBA7300954", "20240421_LEB3");
#   mac_to_NameDict.set("A0DD6C0EFD28", "20240421_LEB4");
#   mac_to_NameDict.set("10061C684D28", "20240421_LEB5");
#   mac_to_NameDict.set("A0B765F51E28", "MockingKrake_LEB");
#   mac_to_NameDict.set("3C61053DC954", "Not Homework2, Maryville TN");
# }//end setup mac_to_NameDict

# TOPIC = "F4650BC0B52C_ALM"

# ============================================================
# Config Loader
# ============================================================

def load_config(path: str) -> dict:
    # utf-8-sig safely handles BOM if present
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)

# ============================================================
# Alarm Severity Definition
# ============================================================

class AlarmLevel(IntEnum):
    INFORMATIONAL = 1
    PROBLEM = 2
    WARNING = 3
    CRITICAL = 4
    PANIC = 5

# ============================================================
# ADaM Server
# ============================================================

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
        self.policy = "POLICY0"
        self.annunciators: list[str] = []

        self.client = mqtt.Client(
            client_id=client_id,
            callback_api_version=mqtt.CallbackAPIVersion.VERSION1
        )

        if username and password:
            self.client.username_pw_set(username, password)

        self.client.on_message = self.on_message
        self.client.connect(broker_host, broker_port)

        self.client.subscribe(self.alarm_topic, qos=1)
        self.client.subscribe(self.ack_topic, qos=1)

        self.client.loop_start()

        print("[ADaM] Server started")
        print(f"[ADaM] Alarm topic: {self.alarm_topic}")
        print(f"[ADaM] ACK topic:   {self.ack_topic}")

    # ========================================================
    # MQTT Routing
    # ========================================================

    def on_message(self, client, userdata, msg):
        payload = msg.payload.decode("utf-8")

        if msg.topic == self.alarm_topic:
            self.handle_alarm(payload)
        elif msg.topic == self.ack_topic:
            self.handle_ack(payload)

    # ========================================================
    # Alarm Intake
    # ========================================================

    def handle_alarm(self, payload: str):
        try:
            alarm = json.loads(payload)
        except json.JSONDecodeError:
            print("[ADaM] Invalid alarm JSON")
            return

        alarm_id = alarm.get("alarm_id")
        severity = alarm.get("severity")

        print(f"[ADaM] Alarm received → id={alarm_id}, severity={severity}")

        # IMPORTANT CHANGE:
        # Server forwards EVERY alarm regardless of policy.
        # Policy is enforced in subscriber storage/ordering.
        self.forward_to_annunciators(alarm)

    def forward_to_annunciators(self, alarm: dict):
        alarm_id = alarm.get("alarm_id")
        severity = alarm.get("severity")

        for topic in self.annunciators:
            self.client.publish(topic, json.dumps(alarm), qos=1)
            # Keep the log style you asked for
            print(f"[ADaM] {self.policy} → forwarding severity {severity} (id={alarm_id})")

    # ========================================================
    # ACK Handling
    # ========================================================

    def handle_ack(self, payload: str):
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return

        print(
            f"[ADaM] ACK received → "
            f"alarm_id={data.get('alarm_id')} "
            f"status={data.get('status')}"
        )

    # ========================================================
    # Shutdown
    # ========================================================

    def stop(self):
        self.client.loop_stop()
        self.client.disconnect()
        print("[ADaM] Server stopped")

# ============================================================
# Main Entry Point
# ============================================================

def main():
    config_path = os.path.join(
        os.path.dirname(__file__),
        "config",
        "adam_config.json"
    )

    config = load_config(config_path)

    server = ADaMServer(
        broker_host="public.cloud.shiftr.io",
        broker_port=1883,
        alarm_topic=config["alarm_topic"],
        ack_topic=config["ack_topic"],
        username="public",
        password="public",
    )

    server.policy = config.get("policy", "POLICY0")
    server.annunciators = config.get("annunciators", [])

    print(f"[ADaM] Policy:      {server.policy}")
    print(f"[ADaM] Annunciators: {server.annunciators}")

    try:
        while True:
            pass
    except KeyboardInterrupt:
        server.stop()

if __name__ == "__main__":
    main()
