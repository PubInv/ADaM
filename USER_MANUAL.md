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

## 2) Download Python on your machine
Go to https://www.python.org/downloads/ and download Python version 3.10 or higher.
Then check if it has been installed in your machine by,
### WINDOWS:
```powershell
Python --v
```

### MAC:
```
python3 --version
```


## 3) Create and activate a virtual environment

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

## 4) Install dependencies
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

## 5) Configure ADaM

Inside the folder "ADaMpy", create your .env file. This file will contain information about your server. You can follow the file "Example.env"
for reference.

Things you must set correctly:
- broker_host, broker_port  
- username, password (or use env vars below)  

DO NOT COMMIT YOUR .ENV FILE.
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

## 6) Run the system (3 terminals)

Open three terminals. In each terminal:
- cd to repo root (folder that contains ADaMpy/)
- activate the venv
- run the following commands

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

## 7) Running The ADaM Web App
The web app is another method to experience ADaM. It provides a more visual logging system and enables you to simulate
virtual Krakes as well as configuring a physical Krake on it. To open it:
In your corresponding terminal, go to the directory that says "ADaM", then:
``` Windows
python -m ADaMpy.app
```
``` MAC
python -m ADaMpy.app
```
Then, copy the web URL shown in the terminal onto a browser.

## 8) Running the ADaM App
1. The ADaM app is hosted using Expo Go, you can download the app on the App Store and Google Play.
2. Go to https://nodejs.org/en/download and download NodeJS for your operating system and follow the installation instructions.
3. Open your IDE, and change the folder to the "Mobile" folder
4. In the terminal, type:
   ```
    npm install
   ```
5. Then, type this command
  ```
  npx expo start
  ```
6. A QR code will be shown on the screen, scan it on your mobile device for the app to boot

The ADaM app acts as a subscriber, the user will be able to see any incoming topics and also be able to respond to them and send the
response back to the server.
