import time
import paho.mqtt.client as mqtt

broker_address = "broker.hivemq.com" 
broker_port = 1883
topic = "test topic to see if this code works"

#creating a new MQTT client
client = mqtt.Client(client_id="PythonSender", protocol=mqtt.MQTTv311)

#connect to broker
client.connect(broker_address, broker_port)

print(f"connected to MQTT broker at {broker_address}:{broker_port}")
print("type 'exit' to quit")

while True:
    message = input("enter message to send: ")
    if message.lower() == "exit":
        break

    #publish the message
    client.publish(topic, message)
    print(f"Sent: {message}")

#disconnect from the broker
client.disconnect()
print("Disconnected from broker")




#TODO
# So this program worked, what we need to do now is integrate the subscriber program that Rob made so that we can make more testing.
# We have to create a python virtual environment first so we don't run into potential version difference problems(Have to do some research on how to do that) but the way 
# to do that in the terminal is run the "python -m venv mohamadenv" command.
# Expand on this program by creating classes, these classes are going to be responsible for classifying the different types of alarms and how critical they are going to be
# (Going to need lots of research on this)