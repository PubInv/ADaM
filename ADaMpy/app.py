from flask import Flask, render_template, request, jsonify
from pathlib import Path
from datetime import datetime
import logging
import paho.mqtt.client as mqtt
import uuid


from ADaMpy.gpad_api import (
    encode_gpap_alarm,
    decode_gpap_alarm,
    decode_gpap_response,
)

from ADaMpy.alarm_db import (
    load_alarm_database,
    extract_alarm_type_key,
    strip_alarm_type_marker,
)


app = Flask(__name__)

ADAMPY_DIR = Path(__file__).resolve().parent
LOG_FILE = ADAMPY_DIR / "adam_server.log"
CONFIG_FILE = ADAMPY_DIR / "config" / "adam_config.json"
ALARM_TYPES_FILE = ADAMPY_DIR / "config" / "alarm_types.json"

# Later take this from the configuation file
app.config['MQTT_BROKER_URL'] = 'public.cloud.shiftr.io'
app.config['MQTT_BROKER_PORT'] = 1883
username = 'public'
password = 'public'

kwargs = {"client_id": f"ADaMServer-{uuid.uuid4().hex[:6]}"}

client = mqtt.Client(**kwargs)
if username and password:
    client.username_pw_set(username, password)

#client.on_connect = self.on_connect
#client.on_message = self.on_message


def read_last_lines(path: Path, limit: int = 30):
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        return [line.rstrip("\n") for line in lines[-limit:]]
    except Exception as e:
        return [f"Error reading file: {e}"]


@app.route("/")
def home():
    recent_logs = read_last_lines(LOG_FILE, 10)
    return render_template(
        "home.html",
        now=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        log_exists=LOG_FILE.exists(),
        config_exists=CONFIG_FILE.exists(),
        alarm_types_exists=ALARM_TYPES_FILE.exists(),
        recent_logs=recent_logs
    )


@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "service": "ADaM Flask UI",
        "time": datetime.now().isoformat(),
        "log_file_exists": LOG_FILE.exists(),
        "config_exists": CONFIG_FILE.exists(),
        "alarm_types_exists": ALARM_TYPES_FILE.exists()
    })


@app.route("/logs")
def logs():
    logs = read_last_lines(LOG_FILE, 100)
    return render_template("logs.html", logs=logs, log_file=str(LOG_FILE))


@app.route("/manual-alarm", methods=['GET', 'POST'])
def manual_alarm():
    if request.method == 'POST':
        alarm_content = request.form.get('alarm_content')
        app.logger.info('You submitted an alarm.')
        app.logger.info(alarm_content)
        message="Hello, World!"
        topic="adam/out/PubInv-test27"

        annunciator_topic = "adam/out/PubInv-test273-ALM"
        payload = encode_gpap_alarm(
#            alarm.severity,
#            self._format_alarm_for_display(alarm),
#            msg_id=alarm.msg_id,
3,
"spud",
"ABCDE367",
            max_len=80,
        )
        client.publish(annunciator_topic, payload, qos=1)
        app.logger.info("published!")

    return render_template("manual_alarm.html")


@app.route("/krakes")
def krakes():
    return render_template("krakes.html")


@app.route("/config")
def config_page():
    return render_template(
        "config.html",
        config_file=str(CONFIG_FILE),
        alarm_types_file=str(ALARM_TYPES_FILE)
    )


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
