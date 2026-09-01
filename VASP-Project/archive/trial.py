from awscrt import io, mqtt
from awsiot import mqtt_connection_builder
import time

# ---------------- AWS IoT Settings ----------------
ENDPOINT = "amu2pa1jg3r4s-ats.iot.ap-south-1.amazonaws.com"  # replace with your AWS IoT endpoint
CLIENT_ID = "Raspberry"
TOPIC = "sdk/test/python"

# ---------------- Certificate Paths ----------------
PATH = "/home/pi_123/aws_iot/"
CERT = PATH + "c5811382f2c2cfb311d53c99b4b0fadf4889674d37dd356864d17f059189a62d-certificate.pem.crt"
KEY = PATH + "c5811382f2c2cfb311d53c99b4b0fadf4889674d37dd356864d17f059189a62d-private.pem.key"
ROOT = PATH + "AmazonRootCA1.pem"

# ---------------- Build MQTT Connection ----------------
mqtt_connection = mqtt_connection_builder.mtls_from_path(
    endpoint=ENDPOINT,
    cert_filepath=CERT,
    pri_key_filepath=KEY,
    client_id=CLIENT_ID,
    ca_filepath=ROOT,
    keep_alive_secs=60  # sends ping every 60 seconds to keep connection alive
)

print("Connecting to AWS IoT...")
connect_future = mqtt_connection.connect()
connect_future.result()
print("Connected!")

# ---------------- Function to Disconnect ----------------
def disconnect():
    print("Disconnecting from AWS IoT...")
    mqtt_connection.disconnect()
    print("Disconnected!")

# ---------------- Publish Loop ----------------
try:
    while True:
        message = "Hello from Raspberry Pi!"
        mqtt_connection.publish(
            topic=TOPIC,
            payload=message,
            qos=mqtt.QoS.AT_LEAST_ONCE
        )
        print(f"Published message to '{TOPIC}': {message}")
        time.sleep(5)  # publish every 5 seconds

except KeyboardInterrupt:
    # When you press Ctrl+C, it will disconnect cleanly
    disconnect()
