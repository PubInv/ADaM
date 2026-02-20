## Clone, setup, and run (Windows + macOS)

### 0) Prerequisites
- Git installed
- Python 3.10+ installed
- An MQTT broker reachable from your machine
- Repo root must contain `ADaMpy/` (that is how the commands below work)

---

## 1) Clone the repo

### Windows (PowerShell)
```powershell
cd $HOME
git clone https://github.com/PubInv/ADaM.git
cd ADaM
```

### macOS (Terminal)
```bash
cd ~
git clone https://github.com/PubInv/ADaM.git
cd ADaM
```

Verify you are in the correct folder.  
You must see **ADaMpy/** in the listing.

**Windows**
```powershell
dir
```

**macOS**
```bash
ls
```

---

## 2) Create and activate a virtual environment

### Windows (PowerShell)
```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python --version
```

If PowerShell blocks activation:
```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
.\.venv\Scripts\Activate.ps1
```

### Windows (cmd)
```cmd
py -m venv .venv
.\.venv\Scripts\activate.bat
python --version
```

### macOS
```bash
python3 -m venv .venv
source .venv/bin/activate
python --version
```

---

## 3) Install dependencies
```bash
python -m pip install --upgrade pip
python -m pip install paho-mqtt
```
How to check if it worked
```
python -m pip show paho-mqtt
```

If installed, it prints package details(name, version, location)
---

## 4) Configure ADaM

Edit:
```
ADaMpy/config/adam_config.json
```

Minimum things you must set correctly:
- broker_host, broker_port  
- username, password (or use env vars below)  
- alarm_topic  
- ack_topic  
- annunciators (must contain at least one annunciator topic)

Sanity check:  
If `annunciators` is empty, nothing will ever display in Krake.

---

### Setting MQTT credentials locally using environment variables (do not commit)

If you removed `username` and `password` from `ADaMpy/config/adam_config.json`, set them locally before running ADaM.

Environment variables to set:
- `ADAM_MQTT_USERNAME`
- `ADAM_MQTT_PASSWORD`

Note: These variables only matter if the ADaM scripts read them. If the code does not read env vars, setting them will have no effect.

#### Windows PowerShell (current terminal session only)
```powershell
$env:ADAM_MQTT_USERNAME = "public"
$env:ADAM_MQTT_PASSWORD = "public"
```

Verify:
```powershell
echo $env:ADAM_MQTT_USERNAME
```

#### Windows PowerShell (persist for your user account)
```powershell
[Environment]::SetEnvironmentVariable("ADAM_MQTT_USERNAME", "public", "User")
[Environment]::SetEnvironmentVariable("ADAM_MQTT_PASSWORD", "public", "User")
```

Close and reopen PowerShell, then verify:
```powershell
echo $env:ADAM_MQTT_USERNAME
```

#### Windows cmd (current terminal session only)
```cmd
set ADAM_MQTT_USERNAME=public
set ADAM_MQTT_PASSWORD=public
```

Verify:
```cmd
echo %ADAM_MQTT_USERNAME%
```

#### Windows cmd (persist for your user account)
```cmd
setx ADAM_MQTT_USERNAME "public"
setx ADAM_MQTT_PASSWORD "public"
```

Close and reopen cmd to apply.

#### macOS Terminal (current terminal session only)
```bash
export ADAM_MQTT_USERNAME="public"
export ADAM_MQTT_PASSWORD="public"
```

Verify:
```bash
echo $ADAM_MQTT_USERNAME
```

#### macOS Terminal (persist)

Add these lines to your shell profile:

zsh → `~/.zshrc`  
bash → `~/.bashrc`

```bash
export ADAM_MQTT_USERNAME="public"
export ADAM_MQTT_PASSWORD="public"
```

Reload:
```bash
source ~/.zshrc
```

If you want this to be usable when removing creds from the config, the code must read these env vars.

---

## 5) Run the system (3 terminals)

Open three terminals. In each terminal:
- cd to repo root (folder that contains ADaMpy/)
- activate the venv
- run the command

### Terminal 1: Start ADaMServer

**Windows (PowerShell)**
```powershell
cd path\to\ADaM
.\.venv\Scripts\Activate.ps1
python -m ADaMpy.ADaMServer
```

**macOS**
```bash
cd /path/to/ADaM
source .venv/bin/activate
python -m ADaMpy.ADaMServer
```

---

### Terminal 2: Start Krake Simulator

Default annunciator:
```bash
python -m ADaMpy.Krake_Simulator
```

Specific annunciator topic:
```bash
python -m ADaMpy.Krake_Simulator "adam/out/LEBANON-5"
```

---

### Terminal 3: Start an alarm producer

Option A:
```bash
python -m ADaMpy.simulators.alarm_generator
```

Option B:
```bash
python -m ADaMpy.simulators.manual_alarm_test
```

---

## 6) If something fails, check these first

- You are running from repo root (folder containing ADaMpy/)
- Your venv is activated
- ADaMpy/config/adam_config.json exists and broker creds are correct
- annunciators[] is not empty
- You are not using placeholder broker credentials