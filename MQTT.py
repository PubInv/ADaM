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
