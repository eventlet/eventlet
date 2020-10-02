import paho.mqtt.client as mqtt 

def on_connect(client, userdata, flags, rc):
   print("[+] Connection successful")
   client.subscribe('#', qos = 1)        # Subscribe to all topics
   client.subscribe('$SYS/#')            # Broker Status (Mosquitto)
def on_message(client, userdata, msg):
   print('[+] Topic: %s - Message: %s' % (msg.topic, msg.payload))

client = mqtt.Client(client_id = "MqttClient")
client.on_connect = on_connect
client.on_message = on_message
client.connect('<IP>', 1883, 60)
client.loop_forever()
