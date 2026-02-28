# This file is responsible for loading and validating the alarm database from a JSON file.
# It defines the expected structure of the alarm database and provides a function to load it into a Python 
# dictionary for use by the rest of the application.

# in alarm_database.json, we expect an object with a "version" string and an "alarm_types" array. Each entry in
# "alarm_types" must be an object with the following fields:
# - alarm_key (string): a unique identifier for the alarm type
# - alarm_number (string): a human-readable code for the alarm
# - alarm_message (string): a template message for the alarm
# - severity (int): the severity level of the alarm (e.g. 1-5)
# - audio_file (string): the filename of the audio to play for this alarm
# - actions (array of strings): a list of actions that can be taken for this alarm

# alarm key is the unique internal identifier for an alarm type. 
# Example:
# door_open
#water_leak

# the way to choose an alarm key is to, 1 - use lowercase. 2 - use underscores instead of spaces. 
#                                       3 - make it descriptive but concise. 4 - avoid special characters.

# To add a new alarm type safely, you would:
#Open alarm_database.json
#Copy an existing alarm entry.
#Paste it at the end of the alarm_types array.

#Modify:
#alarm_key → must be unique
#alarm_number → must be unique
#Update text, severity, audio, actions

#Validate:
#No duplicate alarm_key
#No duplicate alarm_number
#Severity is 1–5
#actions is an array of strings
#Save the file.


import json
import os
from typing import Any

REQUIRED_FIELDS = [
    "alarm_key",
    "alarm_number",
    "alarm_message",
    "severity",
    "audio_file",
    "actions",
]

def default_db_path() -> str:
    # Path relative to this file: ADaMpy/config/AlarmDatabase.json
    base = os.path.abspath(os.path.dirname(__file__))
    return os.path.join(base, "config", "alarm_database.json")

def load_alarm_database(path: str | None = None) -> dict[str, dict[str, Any]]:
    if path is None:
        path = default_db_path()

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    alarm_types = data.get("alarm_types")
    if not isinstance(alarm_types, list):
        raise ValueError("alarm_database.json must contain an 'alarm_types' array")

    lookup: dict[str, dict[str, Any]] = {}

    for i, entry in enumerate(alarm_types):
        if not isinstance(entry, dict):
            raise ValueError(f"alarm_types[{i}] must be an object")

        for field in REQUIRED_FIELDS:
            if field not in entry:
                raise ValueError(f"alarm_types[{i}] missing required field '{field}'")

    if not isinstance(entry["alarm_key"], str):
        raise ValueError(f"alarm_types[{i}].alarm_key must be a string")
    if not isinstance(entry["alarm_number"], str):
        raise ValueError(f"alarm_types[{i}].alarm_number must be a string")
    if not isinstance(entry["alarm_message"], str):
        raise ValueError(f"alarm_types[{i}].alarm_message must be a string")
    if not isinstance(entry["severity"], int):
        raise ValueError(f"alarm_types[{i}].severity must be an int")
    if not isinstance(entry["audio_file"], str):
        raise ValueError(f"alarm_types[{i}].audio_file must be a string")
    if not isinstance(entry["actions"], list) or not all(isinstance(a, str) for a in entry["actions"]):
        raise ValueError(f"alarm_types[{i}].actions must be a list of strings")


    key = entry["alarm_key"]
    if key in lookup:
        raise ValueError(f"Duplicate alarm_key '{key}'")

    lookup[key] = entry

    return lookup


