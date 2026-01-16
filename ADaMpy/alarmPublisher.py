from enum import IntEnum
import json
import uuid
from datetime import datetime, timezone
import threading
import paho.mqtt.client as mqtt

# Improvements:
# 1. IMPORTANT: allow deletion from currentAlarms
# 2. change names to Krake names
# 3. remove duplication of names in two places
# 4. Add timestamps
# 5. Need a function for generating unique ids

# 5 levels for the alarm
# TODO: change to use the Krake standard levels and names

alarms_lock = threading.Lock()
class AlarmLevel(IntEnum):
    """Standardized levels 1–5."""
    INFORMATIONAL = 1
    PROBLEM = 2
    WARNING = 3
    CRITICAL = 4
    PANIC = 5

default_names = {
    AlarmLevel.INFORMATIONAL: "Informational",
    AlarmLevel.PROBLEM: "Problem",
    AlarmLevel.WARNING: "Warning",
    AlarmLevel.CRITICAL: "Critical",
    AlarmLevel.PANIC: "Panic",
}

class Alarm:
#    alarm_id: str,
#    level: AlarmLevel,
#    descr: str,
#    timestamp: str
    def __init__(self, alarm_id: str, level:AlarmLevel, descr:str | None):
    # Instance attributes (unique to each dog object)
        self.alarm_id = alarm_id
        self.level = level
        self.description = descr



# This will hold the current alarms
currentAlarms = []

# Here we will add our first intellgent Alarm publication Policy...


class AlarmPublisher:
    """
    Wraps paho-mqtt for sending structured alarm messages.
    """

    def __init__(
        self,
        broker_address: str,
        broker_port: int = 1883,
        topic: str = "alarms/default",
        client_id: str = "AlarmPublisher",
        protocol=mqtt.MQTTv311,
        qos: int = 1,
        retain: bool = False,
        level_names: dict | None = None,
        ack_topic: str | None = None,  # where receivers should send acks (optional)
        event_topic: str | None = None,
    ):
        # Configure MQTT client
        self.client = mqtt.Client(client_id=client_id, protocol=protocol)
        self.client.connect(broker_address, broker_port)
        self.client.loop_start()

        self.topic = topic
        self.event_topic = event_topic or (topic + "/events")
        self.qos = qos
        self.retain = retain
        self.ack_topic = ack_topic

        default_names = {
            AlarmLevel.INFORMATIONAL: "Informational",
            AlarmLevel.PROBLEM: "Probelm",
            AlarmLevel.WARNING: "Warning",
            AlarmLevel.CRITICAL: "Critical",
            AlarmLevel.PANIC: "Panic",
        }

        if level_names:
            default_names.update(level_names)

        self.level_names = default_names

    def send_alarm(
        self,
        level: AlarmLevel,
        description: str | None = None,
        **extra_fields,
    ) -> str:
        """
        Publish an alarm message as JSON and return the alarm_id.
        """
        alarm_id = str(uuid.uuid4())  # unique ID for this alarm

        payload = {
            "alarm_id": alarm_id,
            "level": int(level),
            "label": self.level_names[level],
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        if description:
            payload["description"] = description

        if self.ack_topic is not None:
            payload["ack_topic"] = self.ack_topic

        # Allow callers to add custom fields
        if extra_fields:
            payload.update(extra_fields)

        data = json.dumps(payload)
        self.client.publish(self.topic, data, qos=self.qos, retain=self.retain)

        log_entry = {
            "alarm_id": alarm_id,
            "level": int(level),
            "label": self.level_names[level],
            "description": description,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "topic": self.topic,
}

        with open("sent_alarms.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")

        return alarm_id
    
    def dismiss_alarm(self, alarm_id: str, **extra_fields) -> None:
        payload = {
            "event": "dismissed",
            "alarm_id": alarm_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if extra_fields:
            payload.update(extra_fields)

        self.client.publish(self.event_topic, json.dumps(payload), qos=self.qos, retain=False)


    def close(self):
        self.client.loop_stop()
        self.client.disconnect()

def printAlarm(alarm):
     print(
                f"Alarm {alarm.alarm_id} | "
                f"level {int(alarm.level)} ({default_names[alarm.level]}) | "
                f"description: {alarm.description}"
            )
def printAlarmList(alarms):
    print("Current Alarms:")
    for alarm in alarms:
        printAlarm(alarm)
    print("End of Current Alarms")


def main():
    # === CONFIG: adjust these to match your subscriber ===
    broker_address = "broker.mqttdashboard.com"
    broker_port = 1883

    # This should match the topic your subscriber listens to
    alarm_topic = "PubInv-test973/krake"          # incoming for alarms
    ack_topic = "PubInv-test973/acks"       # where acks will be sent

    publisher = AlarmPublisher(
        broker_address=broker_address,
        broker_port=broker_port,
        topic=alarm_topic,
        client_id="PythonAlarmSender",
        ack_topic=ack_topic,
    )

    print(f"Connected to MQTT broker at {broker_address}:{broker_port}")
    print(f"Publishing alarms to topic: {alarm_topic}")
    print(f"Expecting ACKs on topic:    {ack_topic}")
    print()
    print("Usage:")
    print("  Type: <level 1-5> <optional description>")
    print("  Example: 3 door left open")
    print("  Example: 5 fire in lab 2")
    print("  Type 'exit' to quit.\n")
    printAlarmList(currentAlarms)

    try:
        while True:
            # Make this take a letter as an initial command like:
            # a3 hair on fire / add level-3 alarm
            # d2 / delete alarm number 2 if it exists
            raw = input("Alarm> ").strip()
            if not raw:
                continue
            if raw.lower() == "exit":
                break

            if raw.upper().startswith("D-"):
                try:
                    idx = int(raw.split("-",1)[1])
                except ValueError:
                    print(" Use D-<n> to dismiss alarm #n")
                    continue

                if idx < 1 or idx > len(currentAlarms):
                    print(f" No alarm #{idx} to dismiss.")
                    continue

                alarm_to_dismiss = currentAlarms[idx - 1]
                publisher.dismiss_alarm(alarm_to_dismiss.alarm_id, dismissed_by="manual-cli")

                currentAlarms.pop(idx - 1)
                print(f" Dismissed alarm #{idx} (alarm_id={alarm_to_dismiss.alarm_id})")
                printAlarmList(currentAlarms)
                continue

            parts = raw.split(maxsplit=1)
            level_str = parts[0]
            description = parts[1] if len(parts) > 1 else None

            # Validate level
            try:
                level_num = int(level_str)
                level = AlarmLevel(level_num)
            except (ValueError, KeyError):
                print("Please start with a number 1–5 for the alarm level.")
                continue

# TODO: rewrite this to accept an Alarm object as a parameter
            alarm_id = publisher.send_alarm(
                level,
                description=description,
                source="manual-cli",  # example extra field
            )
# Now we construct an Alarm object,
# add it to current Alarms, and then send it.
            newAlarm = Alarm(alarm_id, level, description)
            currentAlarms.append(newAlarm)



            print(
                f"Sent alarm {alarm_id} | "
                f"level {int(level)} ({publisher.level_names[level]}) | "
                f"description: {description}"
            )
            printAlarmList(currentAlarms)
    finally:
        publisher.close()
        print("Disconnected from broker.")


if __name__ == "__main__":
    main()

    

    #Note, maybe I should ask Rob on how to approach this, should i make a mini game-like program where the
    # terminal would send me alarms and then make the user type something to indicate that they completed the
    # alarm so the terminal can send them another alarm and so on. but also give the user the option to dismiss
    # an alarm. SO perhaps it should be something like a TO-DO list, where I present the user with a series of alarms
    # and then give them the optionality to dismiss some and complete some. But then a question appears in my head,
    # IF i go for this approach, do i have to type out the alarms manually? how would an approach like this be scaled?
