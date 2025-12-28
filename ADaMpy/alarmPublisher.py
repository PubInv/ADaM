from __future__ import annotations
from enum import IntEnum
import json
import uuid
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
import threading
import paho.mqtt.client as mqtt

# Improvements:
# 1. IMPORTANT: allow deletion from currentAlarms
# 2. change names to Krake names
# 3. remove duplication of names in two places
# 4. Add timestamps
# 5. Need a function for generating unique ids



alarms_lock = threading.Lock()
class AlarmLevel(IntEnum):
    """Standardized levels 1–5."""
    INFORMATIONAL = 1
    PROBLEM = 2
    WARNING = 3
    CRITICAL = 4
    PANIC = 5

default_names: Dict[AlarmLevel, str] = {
    AlarmLevel.INFORMATIONAL: "Informational",
    AlarmLevel.PROBLEM: "Problem",
    AlarmLevel.WARNING: "Warning",
    AlarmLevel.CRITICAL: "Critical",
    AlarmLevel.PANIC: "Panic",
}

@dataclass
class Alarm:
    """Represents an alarm with a level, description, unique ID, and timestamp."""
    level: AlarmLevel
    description: Optional[str] = None

    alarm_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def label(self, level_names: Dict [AlarmLevel, str]) -> str:
        return level_names.get(self.level, str(int(self.level)))
    
    def to_payload(self, level_names: Dict [AlarmLevel, str],
                  ack_topic: Optional[str] = None,
                  extra_fields: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        payload:Dict[str, Any] = {
            "alarm_id": self.alarm_id,
            "level": int(self.level),
            "label": self.label(level_names),
            "timestamp":self.timestamp,
        }

        if self.description:
            payload["description"] = self.description

        if ack_topic is not None:
            payload["ack_topic"] = ack_topic

        if extra_fields:
            payload.update(extra_fields)

        return payload
    
    def to_log_entry(
            self,
            level_names:Dict[AlarmLevel, str],
            topic: str,
    ) -> Dict[str, Any]:
        return {
            "alarm_id": self.alarm_id,
            "level": int(self.level),
            "label": self.label(level_names),
            "description": self.description,
            "timestamp": self.timestamp,
            "topic": topic,
        }
    

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
        ack_topic: str | None = None,  # where receivers should send acks
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

        self.level_names: Dict[AlarmLevel,str] = dict(default_names)
        if level_names:
            self.level_names.update(level_names)

        

    def send_alarm(self, alarm: Alarm, **extra_fields) -> str:
        payload = alarm.to_payload(
            level_names = self.level_names,
            ack_topic = self.ack_topic,
            extra_fields = extra_fields or None,
        )
        
    
        self.client.publish(self.topic, json.dumps(payload), qos=self.qos, retain=self.retain)

        log_entry = alarm.to_log_entry(
            level_names = self.level_names,
            topic = self.topic,
        )

        with open("sent_alarms.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")

        return alarm.alarm_id
    
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

def print_alarm(alarm: Alarm, level_names:Dict[AlarmLevel, str]) -> None:
     print(
        f"Alarm {alarm.alarm_id} | "
        f"time {alarm.timestamp} | "
        f"level {int(alarm.level)} ({alarm.label(level_names)}) | "
        f"description: {alarm.description}"
    )
     
def print_alarm_list(alarms: list[Alarm], level_names: Dict[AlarmLevel, str]) -> None:
    print("Current Alarms:")
    for alarm in alarms:
        print_alarm(alarm, level_names)
    print("End of Current Alarms")


# This will hold the current alarms
currentAlarms = []

def main():
    # === CONFIG: adjust these to match your subscriber ===
    broker_address = "broker.mqttdashboard.com"
    broker_port = 1883

    # This should match the topic your subscriber listens to
    alarm_topic = "PubInv-test973"          # incoming for alarms
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
    print_alarm_list(currentAlarms, publisher.level_names)

    try:
        while True:
            
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
                print_alarm_list(currentAlarms, publisher.level_names)
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


# Now we construct an Alarm object,
# add it to current Alarms, and then send it.
            newAlarm = Alarm(level=level, description=description)
            #newAlarm = Alarm(level=level, description=description)
            currentAlarms.append(newAlarm)

            publisher.send_alarm(newAlarm, source="manual-cli")

            print(
                f"Sent alarm {newAlarm.alarm_id} | "
                f"time {newAlarm.timestamp} | "
                f"level {int(level)} ({publisher.level_names[level]}) | "
                f"description: {description}"
            )
            print_alarm_list(currentAlarms, publisher.level_names)

    finally:
        publisher.close()
        print("Disconnected from broker.")


if __name__ == "__main__":
    main()

    #TODO
    #Create a Log feature for this program that stores information about the alarm such as
    # alarm level / time of the alarm / description of the alarm.
    # make the user somehow type something to indicate that they completed the alarm and then
    # give the user another alarm to do and so on.
    # store these alarms in a text file or something and give the user the ability to dismiss an
    # alarm and make sure to delete that from the text file.

