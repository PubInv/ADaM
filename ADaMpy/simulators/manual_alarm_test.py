from ADaMpy.gpad_api import (
    encode_gpad_alarm,
    decode_gpad_alarm,
    encode_gpad_ack,
    decode_gpad_ack,
)
import paho.mqtt.client as mqtt


BROKER = "public.cloud.shiftr.io"
PORT = 1883
TOPIC = "adam/in/alarms"


client = mqtt.Client(
    client_id="manual_alarm_test",
    callback_api_version=mqtt.CallbackAPIVersion.VERSION1
)
client.username_pw_set("public", "public")
client.connect(BROKER, PORT)
client.loop_start()

while True:
    desc = input("Alarm description: ")
    sev = int(input("Severity (1-5): "))

    msg = encode_gpad_alarm(sev, desc)

    client.publish(TOPIC, msg, qos=1)
    print("Alarm sent\n")
