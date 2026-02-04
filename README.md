# ADaM - Alarm Dialog Management

Here's the link to test our live site:

[https://pubinv.github.io/ADaM/](https://pubinv.github.io/ADaM/)


This is a new project that has grown out of the [General Purpose Alarm Device](https://github.com/PubInv/general-purpose-alarm-device) project
and its successor, the [Krake](https://github.com/PubInv/krake).

Our goal is to develop an algorithm or other software system for managing human attention to complex, overlapping and ambiguous alarms, such as occur
in an intensive care unit (ICU). This is related to but extends the ideas in the scientific literature called "Intelligent Alarm Systems" and 
the well-observed phemonemanon of alarm fatique.  The whole field of alarm management is complex, and we have not fully researched it.

Nonetheless, we are not aware of anyone attempting to manage the "alarm dialog", by which we mean the interplay between the alarm conditions and the human responding to them. Briefly speaking, when an alarm occurs, a human responds to it, perhaps by muting the alarm. However, when 
a crisis occurs there may be multiple alarm conditions which are coming and going. These need to be prioritized.
The fundamental goal of managing this dialog is to allow a human being to make the best decisions possible during the crisis. 

Our goals are to build a system that:
1. Records all interactions for post-hoc interaction.
2. Present the highest priority problem to the human responder.
3. Manage the de-escalation of alarm levels without allowing any needed action to be forgotten.
4. Manage new incoming alarm conditions so they are correctly presented to the responder.
5. Allow alarm muting so the responder can work without distraction but without becoming ignorant of important information.

We foresee a system that is remembering a number of alarm conditions that are evolving over time. Unlike primitive alarm condtions, these
events should be given identities so that they can be correctly dismissied without confusion.

A necessary part of this project will be psychological testing. For example, we can imagine a test regime consisting of an incoming alarm schedule.
Two different ADaMs can be compared based on how effectively they allow a human being to process the alarm responses in a test environment.

A different way of thinking about this is that ADaM does:
1. Logging
2. Anunciation Management (send alarms to mulitple annunciators)
3. Resolution Management (that is, managing Resolutions and Dismissals)
4. Process Management (that is, managing Acknowledgment and Shelving)
5. Time Managment (that is, managing the need to mutings which are of limited time, reminding the operator of open alarm conditions, managing re-alarming of particular conditions).

# Diagram

Our basic architecture. It is important to understand that every domain requires a small amount of configuraiton. It is our goal to move this from "coding" to "configuration", so that a complete, custom domain of alarms can be created with no programming.

<img width="960" height="720" alt="Adam Architecture (1)" src="https://github.com/user-attachments/assets/9c86fe4e-2568-4832-90fe-85d285ba0ca9" />

Below, find an "action sequence diagram":


<img width="960" height="720" alt="Dialog Management Action Diagram" src="https://github.com/user-attachments/assets/296977ea-4a8c-47f6-ba21-d5bd2023eb23" />

# License

All work in this Repo will be released under the fiercely open source [Public Invention Free-Culture License Guidelines](https://github.com/PubInv/PubInv-License-Guidelines).

# Volunteers

This project is just beginning. We welcome volunteers. We need scholaraly researchers, theoreticians, human-computer interaction experts, medical experts, psychologists, computer programmers, graphic artists and technical writers.

A person with the initiative to code a system in Python or preferably Javascript would be extremely valuable if they had the ability to suggest an initial theoretical approach.

# Research

We need a scholar to do some hours of research with Google Scholar to find out how much, if any, of this idea has been addressed already.

One starting point may be:

[https://github.com/PubInv/ADaM](https://github.com/PubInv/ADaM)


The search term "Intelligent Alarm System" does not appear to be exactly what we mean:

["The intelligent alarm management system", Jun Liu, Khiang Wee Lim, Weing Khuen Ho, Kay Chen Tan, Rajagopalan Srinivasan, Arthur Tay. IEEE Software, 2003.](https://www.researchgate.net/profile/Rajagopalan-Srinivasan-3/publication/3247961_The_intelligent_alarm_management_system/links/5860c85008ae329d61fcb03a/The-intelligent-alarm-management-system.pdf)


# ADaM Setup and Run Guide (Windows PowerShell)

## What this project is
ADaM is an MQTT-based alarm router. Producers publish alarms to ADaMServer.
ADaMServer stores all unacknowledged alarms, chooses the next alarm using a Strategy policy (POLICY0 / SEVERITY / SEVERITY_PAUSE), and publishes the chosen alarm to Krake_Simulator.
Krake_Simulator shows only the latest alarm and lets the user ACK it.
ADaMServer logs all key actions for debugging and harm scoring.

---

## Setup (Windows PowerShell)

### 1) Clone repo and go to repo root
```powershell
git clone <REPO_URL>
cd ADaM
```

### 2) Create and activate a virtual environment
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3) Install dependencies
```powershell
# If requirements.txt exists:
pip install -r requirements.txt

# If not, minimum:
pip install paho-mqtt
```

### 4) Set MQTT credentials locally (required)
```powershell
# Set these every time you open a new terminal
$env:MQTT_USER="YOUR_USERNAME"
$env:MQTT_PASS="YOUR_PASSWORD"

# Verify:
echo $env:MQTT_USER
```

---

## Run the system (3 terminals)

Open THREE PowerShell terminals.
In each terminal:

```powershell
cd <path-to-repo>\ADaM
.\.venv\Scripts\Activate.ps1
$env:MQTT_USER="YOUR_USERNAME"
$env:MQTT_PASS="YOUR_PASSWORD"
```

### Terminal 1: Start ADaMServer
```powershell
python .\ADaMServer.py
```

Expected output includes:
- Started policy=...
- Subscribed alarm_topic=... ack_topic=...
- Annunciators=[...]

### Terminal 2: Start Krake Simulator
```powershell
python .\Krake_Simulator.py
```

Krake commands:
- ack  -> acknowledges the currently displayed alarm
- exit -> quits the simulator

### Terminal 3: Start a simulator (choose one)

Random alarm generator:
```powershell
python .\simulators\alarm_generator.py
```

Manual alarm test:
```powershell
python .\simulators\manual_alarm_test.py
```

---

## Policies (Strategy pattern)

ADaMServer uses a Strategy pattern for alarm selection.
Policy is configured in config/adam_config.json.

POLICY0: Baseline/simple policy  
SEVERITY: Highest severity first, ties broken by oldest  
SEVERITY_PAUSE: Like SEVERITY, but enforces a minimum display window

Example config snippet (config/adam_config.json):

```json
{
  "policy": "SEVERITY_PAUSE",
  "severity_pause_seconds": 20.0
}
```

---

## Logging

ADaMServer writes a log file (example: adam_server.log) containing:
- server startup/shutdown
- RECEIVE ALARM
- SEND ALARM
- RECEIVE ACK

---

## Harm score from logs (optional)

```powershell
python .\harm_from_log.py `
  --log "adam_server.log" `
  --from "2026-01-30 01:17:00" `
  --to "2026-01-30 02:18:00" `
  --mode SQUARED `
  --ann "adam/out/LEBANON-5" `
  --normalized_only true
```

Important:
- Use --ann (two dashes), NOT -ann.

---

## Common problems and fixes

### 1) Credentials not set
```powershell
$env:MQTT_USER="YOUR_USERNAME"
$env:MQTT_PASS="YOUR_PASSWORD"
```

### 2) Simulator can’t find config file
- Run from repo root, OR
- Ensure relative path: config/adam_config.json

### 3) Krake display scrolls
- Re-render screen after receive, OR
- Avoid printing while input() waits

### 4) Git push rejected

Safe fix:
```powershell
git pull --rebase origin main
git push origin main
```

Force overwrite (dangerous):
```powershell
git push --force origin main
```