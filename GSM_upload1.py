
#!/usr/bin/env python3

import os
import time
import sqlite3
import json
import ssl
import paho.mqtt.client as mqtt


# ============================================================
# BASE PATH
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "db", "new_db.db")


# ============================================================
# AWS IoT CERTIFICATE PATHS
# ============================================================

CA_PATH = os.path.join(
    BASE_DIR, "certs", "AmazonRootCA1.pem"
)

CERT_PATH = os.path.join(
    BASE_DIR, "certs", "certificate.pem.crt"
)

KEY_PATH = os.path.join(
    BASE_DIR, "certs", "private.pem.key"
)


# ============================================================
# MQTT CONFIGURATION
# ============================================================

MQTT_ENDPOINT = (
    "a1vddjuckiz90j-ats.iot.ap-south-1.amazonaws.com"
)

CLIENT_ID = "Raspberrypi_4A"

TOPIC = f"{CLIENT_ID}/data"


# ============================================================
# DATABASE CONNECTION
# ============================================================

conn = sqlite3.connect(
    DB_PATH,
    check_same_thread=False,
    timeout=10
)

conn.row_factory = sqlite3.Row

cursor = conn.cursor()

# Helps when capture script and uploader access DB together
cursor.execute("PRAGMA journal_mode=WAL")
cursor.execute("PRAGMA busy_timeout=10000")
conn.commit()


# ============================================================
# MQTT CONNECTION STATUS
# ============================================================

mqtt_connected = False


# ============================================================
# MQTT CALLBACKS
# ============================================================

def on_connect(client, userdata, flags, rc):

    global mqtt_connected

    if rc == 0:
        mqtt_connected = True
        print("✅ Connected to AWS IoT Core")

    else:
        mqtt_connected = False
        print(f"❌ MQTT connection failed | rc={rc}")


def on_disconnect(client, userdata, rc):

    global mqtt_connected

    mqtt_connected = False

    print(
        f"⚠️ MQTT disconnected | rc={rc} "
        f"| Automatic reconnect will be attempted..."
    )


# ============================================================
# MQTT CLIENT
# ============================================================

mqtt_client = mqtt.Client(
    client_id=CLIENT_ID,
    protocol=mqtt.MQTTv311
)

mqtt_client.tls_set(
    ca_certs=CA_PATH,
    certfile=CERT_PATH,
    keyfile=KEY_PATH,
    tls_version=ssl.PROTOCOL_TLSv1_2
)

mqtt_client.on_connect = on_connect
mqtt_client.on_disconnect = on_disconnect

# Automatic reconnect delay
mqtt_client.reconnect_delay_set(
    min_delay=1,
    max_delay=30
)

# Start MQTT network loop
mqtt_client.loop_start()


# ============================================================
# INITIAL AWS CONNECTION
# ============================================================

print("🔌 Connecting to AWS IoT Core...")

while not mqtt_connected:

    try:

        mqtt_client.connect(
            MQTT_ENDPOINT,
            port=8883,
            keepalive=60
        )

        # Give callback time to execute
        time.sleep(1)

    except Exception as e:

        print(
            f"❌ MQTT connect failed: {e}"
        )

        time.sleep(2)


print("\n🚀 AWS IoT Offline Uploader Started")
print(f"📂 Database : {DB_PATH}")
print(f"📡 Endpoint : {MQTT_ENDPOINT}")
print(f"📤 Topic    : {TOPIC}")
print()


# ============================================================
# CREATE PAYLOAD FROM DATABASE ROW
# ============================================================

def create_payload(row):

    payload = {

        # ----------------------------------------------------
        # BASIC / PRESSURE DATA
        # ----------------------------------------------------

        "id": row["id"],

        "device_id": row["device_id"],

        "BP_raw": row["BP_raw"],

        "FP_raw": row["FP_raw"],

        "CR_raw": row["CR_raw"],

        "BC_raw": row["BC_raw"],


        # ----------------------------------------------------
        # TIMESTAMP
        # ----------------------------------------------------

        "timestamp": row["timestamp"],


        # ----------------------------------------------------
        # GSM DATA
        # ----------------------------------------------------

        "gsm_status": row["gsm_status"],

        "sim_status": row["sim_status"],

        "sim_iccid": row["sim_iccid"],

        "mobile_number": row["mobile_number"],

        "signal_strength": row["signal_strength"],

        "signal_dbm": row["signal_dbm"],

        "network_status": row["network_status"],

        "operator": row["operator"],

        "latency_ms": row["latency_ms"],


        # ----------------------------------------------------
        # GNSS DATA
        # ----------------------------------------------------

        "gnss_status": row["gnss_status"],

        "latitude": row["latitude"],

        "longitude": row["longitude"],

        "altitude_m": row["altitude_m"],

        "satellites": row["satellites"],

        "gps_utc": row["gps_utc"]
    }

    return payload


# ============================================================
# PUBLISH ONE ROW
# ============================================================

def publish_row(row):

    global mqtt_connected

    row_id = row["id"]

    payload = create_payload(row)

    payload_json = json.dumps(
        payload,
        separators=(",", ":"),
        default=str
    )

    print(
        f"\n📥 Local DB row | "
        f"ID={row_id} | "
        f"Device={row['device_id']} | "
        f"Timestamp={row['timestamp']}"
    )

    print(
        f"   Pressure | "
        f"BP={row['BP_raw']} | "
        f"FP={row['FP_raw']} | "
        f"CR={row['CR_raw']} | "
        f"BC={row['BC_raw']}"
    )

    print(
        f"   GNSS | "
        f"Status={row['gnss_status']} | "
        f"LAT={row['latitude']} | "
        f"LON={row['longitude']} | "
        f"SAT={row['satellites']}"
    )

    print(
        f"   GSM | "
        f"Status={row['gsm_status']} | "
        f"RSSI={row['signal_strength']} | "
        f"dBm={row['signal_dbm']} | "
        f"Network={row['network_status']} | "
        f"Latency={row['latency_ms']} ms"
    )


    # --------------------------------------------------------
    # WAIT FOR MQTT
    # --------------------------------------------------------

    while not mqtt_connected:

        print(
            "⚠️ AWS MQTT disconnected. "
            "Waiting for connection..."
        )

        try:

            mqtt_client.reconnect()

        except Exception as e:

            print(
                f"❌ Reconnect failed: {e}"
            )

        time.sleep(2)


    # --------------------------------------------------------
    # PUBLISH
    # --------------------------------------------------------

    try:

        result = mqtt_client.publish(
            TOPIC,
            payload_json,
            qos=1
        )

        # Check whether publish request was accepted
        if result.rc != mqtt.MQTT_ERR_SUCCESS:

            print(
                f"❌ MQTT publish failed | "
                f"ID={row_id} | rc={result.rc}"
            )

            return False


        # ----------------------------------------------------
        # WAIT FOR QoS 1 PUBLISH COMPLETION
        # ----------------------------------------------------

        result.wait_for_publish(timeout=10)

        if not result.is_published():

            print(
                f"❌ AWS publish not confirmed | "
                f"ID={row_id}"
            )

            return False


        print(
            f"📤 AWS IoT upload successful | "
            f"ID={row_id}"
        )


        # ----------------------------------------------------
        # ONLY AFTER SUCCESSFUL PUBLISH:
        # MARK DATABASE ROW AS UPLOADED
        # ----------------------------------------------------

        cursor.execute(
            """
            UPDATE brake_pressure_log
            SET uploaded = 1
            WHERE id = ?
            """,
            (row_id,)
        )

        conn.commit()

        print(
            f"✅ DB updated | "
            f"ID={row_id} | uploaded=1"
        )

        return True


    except Exception as e:

        print(
            f"❌ Upload failed | "
            f"ID={row_id} | Error={e}"
        )

        return False


# ============================================================
# MAIN UPLOAD LOOP
# ============================================================

try:

    while True:

        # ----------------------------------------------------
        # GET OLDEST UNUPLOADED RECORD
        # ----------------------------------------------------

        try:

            cursor.execute(
                """
                SELECT *
                FROM brake_pressure_log
                WHERE uploaded = 0
                ORDER BY id ASC
                LIMIT 1
                """
            )

            row = cursor.fetchone()

        except sqlite3.Error as e:

            print(
                f"❌ SQLite read error: {e}"
            )

            time.sleep(1)

            continue


        # ----------------------------------------------------
        # NO DATA
        # ----------------------------------------------------

        if row is None:

            time.sleep(0.5)

            continue


        # ----------------------------------------------------
        # UPLOAD ONE RECORD
        # ----------------------------------------------------

        success = publish_row(row)


        # ----------------------------------------------------
        # IF FAILED, KEEP uploaded=0
        # ----------------------------------------------------

        if not success:

            print(
                f"⏳ Keeping ID={row['id']} "
                f"as uploaded=0. Will retry..."
            )

            time.sleep(2)


# ============================================================
# CLEAN EXIT
# ============================================================

except KeyboardInterrupt:

    print(
        "\n🛑 AWS uploader stopped by user."
    )


finally:

    try:

        mqtt_client.loop_stop()

    except Exception:
        pass


    try:

        mqtt_client.disconnect()

    except Exception:
        pass


    try:

        conn.close()

    except Exception:
        pass


    print(
        "🔴 Uploader closed."
    )