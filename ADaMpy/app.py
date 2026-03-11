from flask import Flask, render_template, jsonify
from pathlib import Path
from datetime import datetime

app = Flask(__name__)

ADAMPY_DIR = Path(__file__).resolve().parent
LOG_FILE = ADAMPY_DIR / "adam_server.log"
CONFIG_FILE = ADAMPY_DIR / "config" / "adam_config.json"
ALARM_TYPES_FILE = ADAMPY_DIR / "config" / "alarm_types.json"


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


@app.route("/manual-alarm")
def manual_alarm():
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