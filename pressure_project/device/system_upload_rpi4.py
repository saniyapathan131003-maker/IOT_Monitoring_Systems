import sqlite3
import time
import os
import json
from AWSIoTPythonSDK.MQTTLib import AWSIoTMQTTClient

# ==============================
# PATH CONFIGURATION
# ==============================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CERT_FOLDER = os.path.join(BASE_DIR, "certs")
DB_PATH = os.path.join(BASE_DIR, "db", "new_db.db")

ENDPOINT = "amu2pa1jg3r4s-ats.iot.ap-south-1.amazonaws.com"
PORT = 8883
TOPIC = "brake/data"

ROOT_CA = os.path.join(CERT_FOLDER, "AmazonRootCA1.pem")
CERTIFICATE = os.path.join(CERT_FOLDER, "certificate.pem.crt")
PRIVATE_KEY = os.path.join(CERT_FOLDER, "private.pem.key")

# ==============================
# FETCH DEVICE ID FROM DATABASE
# ==============================
def get_device_id():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT device_id FROM device_config LIMIT 1")
        result = cursor.fetchone()
        conn.close()

        if result:
            print(f"\n The Device id is assigned : {result[0]}\n", flush=True)
            return result[0]
        else:
            print("\n Device id not assigned\n", flush=True)
            return None

    except Exception as e:
        print("Error fetching device_id:", e, flush=True)
        return None


DEVICE_ID = get_device_id()

if DEVICE_ID is None:
    print(" Exiting uploader because device_id is missing.", flush=True)
    exit()

# ==============================
# VERIFY CERTIFICATES
# ==============================
print("🔎 Verifying certificate files...\n", flush=True)

for file_path in [ROOT_CA, CERTIFICATE, PRIVATE_KEY]:
    if not os.path.exists(file_path):
        print(f" Missing file: {file_path}", flush=True)
        exit()
    else:
        print(f"✅ Found: {file_path}", flush=True)

print("Certificate verification successful!\n", flush=True)

# ==============================
# DATABASE CONNECTION
# ==============================
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# Ensure uploaded column exists
cur.execute("PRAGMA table_info(brake_pressure_log)")
columns = [col[1] for col in cur.fetchall()]

if "uploaded" not in columns:
    print("Adding 'uploaded' column...", flush=True)
    cur.execute("ALTER TABLE brake_pressure_log ADD COLUMN uploaded INTEGER DEFAULT 0")
    conn.commit()

print("Uploader Started...\n", flush=True)

# ==============================
# MQTT CLIENT SETUP
# ==============================
mqtt_client = AWSIoTMQTTClient(DEVICE_ID)
mqtt_client.configureEndpoint(ENDPOINT, PORT)
mqtt_client.configureCredentials(ROOT_CA, PRIVATE_KEY, CERTIFICATE)

mqtt_client.configureOfflinePublishQueueing(-1)
mqtt_client.configureDrainingFrequency(2)
mqtt_client.configureConnectDisconnectTimeout(10)
mqtt_client.configureMQTTOperationTimeout(5)

mqtt_client.onOnline = lambda: print(" MQTT Connected to AWS IoT Core", flush=True)
mqtt_client.onOffline = lambda: print("MQTT Disconnected from AWS IoT Core", flush=True)

print("🔌 Connecting to AWS IoT Core...\n", flush=True)
mqtt_client.connect()

# ==============================
# MAIN LOOP
# ==============================
while True:
    try:
        cur.execute("""
            SELECT * FROM brake_pressure_log
            WHERE uploaded = 0 OR uploaded IS NULL
            ORDER BY timestamp ASC
            LIMIT 1
        """)

        row = cur.fetchone()

        if row:
            payload = {
                "Device_id": DEVICE_ID,
                "timestamp": row["timestamp"],
                "bp_raw": row["BP_raw"],
                "bc_raw": row["BC_raw"],
                "cr_raw": row["CR_raw"],
                "fp_raw": row["FP_raw"]
            }

            payload_json = json.dumps(payload)
            payload_pretty = json.dumps(payload, indent=2)

            # Publish to AWS IoT
            mqtt_client.publish(TOPIC, payload_json, 1)

            # Update DB status
            cur.execute(
                "UPDATE brake_pressure_log SET uploaded = 1 WHERE id = ?",
                (row["id"],)
            )
            conn.commit()

            # ================= OUTPUT FORMAT =================
            print("\n================================================", flush=True)
            print("📤 Data Published to AWS IoT Core", flush=True)
            print(f"Device_id = {DEVICE_ID}\n", flush=True)

            print("Data Uploaded :", flush=True)
            print(payload_pretty, flush=True)

            print("\nPayload Sent:", flush=True)
            print(payload_json, flush=True)

            print("================================================\n", flush=True)

        else:
            print("No new data to upload...", flush=True)

        time.sleep(2)

    except Exception as e:
        print("\n Runtime Error:", e, flush=True)
        print("Retrying in 5 seconds...", flush=True)
        time.sleep(5)