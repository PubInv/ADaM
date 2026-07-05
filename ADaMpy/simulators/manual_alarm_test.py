# manual_alarm_test.py is a program very similar to alarm_generator.py, but instead of generating random alarms, 
# it allows the user to input the alarm type and details manually.
#
# Copyright (C) 2026  Saicharan Vishwanatha, Mohamad Mzafar.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import os
import json
import uuid

import paho.mqtt.client as mqtt
from dotenv import load_dotenv

from ADaMpy.gpad_api import encode_gpap_alarm


CFG_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config", "adam_config.json"))


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

# TODO: Move this to a shared library!
def new_msg_id() -> str:
    return uuid.uuid4().hex[:5].upper()


def resolve_alarm_db_path(cfg: dict) -> str:
    configured = str(cfg.get("alarm_db_file", "alarm_types.json")).strip() or "alarm_types.json"
    if os.path.isabs(configured):
        return configured
    return os.path.abspath(os.path.join(os.path.dirname(CFG_FILE), configured))


def load_alarm_type_keys(cfg: dict) -> list[str]:
    path = resolve_alarm_db_path(cfg)
    with open(path, "r", encoding="utf-8-sig") as f:
        data = json.load(f)
    keys = [str(k).strip().upper() for k in (data.get("alarm_types") or {}).keys()]
    keys = [k for k in keys if k]
    keys.sort()
    return keys


def main():
    cfg = load_cfg()

    if not cfg.get("username") or not cfg.get("password"):
        raise RuntimeError(
            "Missing broker credentials. Set BROKER_USERNAME and BROKER_PASSWORD "
            "in your .env file."
        )

    broker = cfg.get("broker_host", "krakepubinv.cloud.shiftr.io")
    port = int(cfg.get("broker_port", 1883))
    user = cfg["username"]
    pw = cfg["password"]
#    topic = cfg.get("alarm_topic", "adam/in/alarms")
    topic = cfg.get("alarm_topic", "F4650BC0B524_ALM")

    known_keys = []
    try:
        known_keys = load_alarm_type_keys(cfg)
    except Exception:
        pass

    client = mqtt.Client(client_id="manual_alarm_test")
    client.username_pw_set(user, pw)
    client.connect(broker, port)
    client.loop_start()

    print(f"[Manual] Publishing GPAP alarms to: {topic}")
    print("[Manual] Typed-alarm format: TYPE:<ALARM_TYPE>|<optional detail>")
    if known_keys:
        print(f"[Manual] Known alarm types: {', '.join(known_keys)}")
    print("[Manual] Ctrl+C to stop\n")

    try:
        while True:
            alarm_type = input("Alarm type key (blank = untyped test): ").strip().upper()
            detail = input("Detail text (optional): ").strip()
            sev = int((input("Severity (0-5): ").strip() or "0"))

            mid = new_msg_id()

            if alarm_type:
                text = f"TYPE:{alarm_type}|{detail}" if detail else f"TYPE:{alarm_type}|"
            else:
                text = detail or "Untyped alarm test"

            msg = encode_gpap_alarm(sev, text, msg_id=mid, max_len=80)
            client.publish(topic, msg, qos=1)
            print(f"Sent: {msg}\n")
            print(f"topic: {topic}\n")

    except KeyboardInterrupt:
        print("\n[Manual] Stopping...")
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
