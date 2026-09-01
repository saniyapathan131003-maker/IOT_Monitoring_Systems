import ssl
import paho.mqtt.client as mqtt

ENDPOINT = "amu2pa1jg3r4s-ats.iot.ap-south-1.amazonaws.com"
TOPIC = "brake/pressure"

def on_connect(client, userdata, flags, rc, properties=None):
    print("Connected:", rc)

def on_publish(client, userdata, mid):
    print("Published:", mid)

client = mqtt.Client(client_id="test123")
client.on_connect = on_connect
client.on_publish = on_publish

client.tls_set(
    ca_certs="/home/pi_123/data/src/pressure_project/raspi/AmazonRootCA1 (4).pem",
    certfile="/home/pi_123/data/src/pressure_project/raspi/3e866ef4c18b7534f9052110a7eb36cdede25434a3cc08e3df2305a14aba5175-certificate.pem.crt",
    keyfile="/home/pi_123/data/src/pressure_project/raspi/3e866ef4c18b7534f9052110a7eb36cdede25434a3cc08e3df2305a14aba5175-private.pem.key",
    tls_version=ssl.PROTOCOL_TLSv1_2
)

client.connect(ENDPOINT, 8883, 60)
client.loop_start()

client.publish(TOPIC, '{"test":123}', qos=1)

# Keep script alive a few seconds to ensure publish
import time
time.sleep(5)
client.loop_stop()
client.disconnect()
