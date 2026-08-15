# alarm_generator.py this program is a simple MQTT client that generates and publishes GPAP alarm messages to a specified topic. 
# It randomly selects alarm types and severity levels from a configured list, encodes the messages in the GPAP format then sends alarms at regular intervals.
#
# Copyright (C) 2026  Saicharan Vishwanatha, Mohamad Mzafar.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU AfferoGeneral Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import os
import json
import time
import random
import uuid
from datetime import datetime, timezone
from dotenv import load_dotenv

import paho.mqtt.client as mqtt

from ADaMpy.gpad_api import encode_gpap_alarm


CFG_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config", "adam_config.json"))

LEVELS = [1, 2, 3, 4, 5]
LABEL = ["", "Informational", "Problem", "Warning", "Critical", "Panic"]


def load_cfg() -> dict:
    load_dotenv()

    with open(CFG_FILE, "r", encoding="utf-8-sig") as f:
        return json.load(f)
    _apply_env_overrides(cfg)
    return cfg

def _apply_env_overrides(cfg: dict) -> None:
    env_map = {
        "broker_host": "BROKER_HOST",
        "broker_port": "BROKER_PORT",
        "username": "BROKER_USERNAME",
        "password": "BROKER_PASSWORD",
    }
    for cfg_key, env_key in env_map.items():
        val = os.environ.get(env_key)
        if val:
            cfg[cfg_key] = val


def new_msg_id() -> str:
    return uuid.uuid4().hex[:5].upper()


def resolve_alarm_db_path(cfg: dict) -> str:
    configured = str(cfg.get("alarm_db_file", "alarm_types.json")).strip() or "alarm_types.json"
    if os.path.isabs(configured):
        return configured
    return os.path.abspath(os.path.join(os.path.dirname(CFG_FILE), configured))


def load_alarm_types(cfg: dict) -> list[tuple[str, str]]:
    path = resolve_alarm_db_path(cfg)
    with open(path, "r", encoding="utf-8-sig") as f:
        data = json.load(f)

    items: list[tuple[str, str]] = []
    for alarm_type, row in (data.get("alarm_types") or {}).items():
        if not isinstance(row, dict):
            continue
        default_text = str(row.get("default_text", alarm_type)).strip()
        items.append((str(alarm_type).strip().upper(), default_text))

    if not items:
        raise RuntimeError(f"No alarm types found in {path}")

    return items


def main():
    cfg = load_cfg()
    topic = cfg.get("alarm_topic", "adam/in/alarms")
    alarm_types = load_alarm_types(cfg)

    client = mqtt.Client(client_id="alarm_generator")
    client.username_pw_set(cfg.get("username", "public"), cfg.get("password", "public"))
    client.connect(cfg.get("broker_host", "krakepublic.cloud.shiftr.io"), int(cfg.get("broker_port", 1883)))
    client.loop_start()

    print(f"[Generator] Publishing GPAP alarms to: {topic}")
    print("[Generator] Publishing typed alarms: TYPE:<ALARM_TYPE>|<optional detail>")
    print("[Generator] Ctrl+C to stop")

    try:
        while True:
            sev = random.choice(LEVELS)
            mid = new_msg_id()

            alarm_type, default_text = random.choice(alarm_types)

            detail = f"src=alarm-generator at={datetime.now(timezone.utc).isoformat()}"
            text = f"TYPE:{alarm_type}|{detail}"

            msg = encode_gpap_alarm(sev, text, msg_id=mid, max_len=80)
            info = client.publish(topic, msg, qos=1)

            if info.rc != 0:
                print(f"[Generator] Publish failed rc={info.rc}")
            else:
                print(f"[Generator] Sent alarm msg_id={mid} type={alarm_type} sev={sev} default='{default_text}' payload={msg}")

            time.sleep(5)

    except KeyboardInterrupt:
        print("\n[Generator] Stopping...")
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
