
#!/usr/bin/env python3

import os
import time
import sqlite3
import json
import ssl
import threading
import paho.mqtt.client as mqtt


# ============================================================
# BASE PATH
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DB_PATH = os.path.join(
    BASE_DIR,
    "db",
    "new_db.db"
)


# ============================================================
# AWS IoT CERTIFICATES
# ============================================================

CA_PATH = os.path.join(
    BASE_DIR,
    "certs",
    "AmazonRootCA1.pem"
)

CERT_PATH = os.path.join(
    BASE_DIR,
    "certs",
    "certificate.pem.crt"
)

KEY_PATH = os.path.join(
    BASE_DIR,
    "certs",
    "private.pem.key"
)


# ============================================================
# AWS MQTT CONFIGURATION
# ============================================================

MQTT_ENDPOINT = (
    "a1vddjuckiz90j-ats.iot.ap-south-1.amazonaws.com"
)

MQTT_PORT = 8883

CLIENT_ID = "Raspberrypi_4A"

TOPIC = f"{CLIENT_ID}/data"


# ============================================================
# MQTT STATUS
# ============================================================

mqtt_connected = False

mqtt_lock = threading.Lock()


# ============================================================
# MQTT CALLBACKS
# ============================================================

def on_connect(client, userdata, flags, rc):

    global mqtt_connected

    if rc == 0:

        mqtt_connected = True

        print()
        print("==================================================")
        print("✅ Connected to AWS IoT Core")
        print(f"📡 Endpoint : {MQTT_ENDPOINT}")
        print(f"📤 Topic    : {TOPIC}")
        print("==================================================")
        print()

    else:

        mqtt_connected = False

        print(
            f"❌ AWS MQTT connection failed | rc={rc}"
        )


def on_disconnect(client, userdata, rc):

    global mqtt_connected

    mqtt_connected = False

    print(
        f"⚠️ MQTT disconnected | rc={rc}"
    )


# ============================================================
# CREATE MQTT CLIENT
# ============================================================

mqtt_client = mqtt.Client(
    client_id=CLIENT_ID,
    protocol=mqtt.MQTTv311
)


# ============================================================
# TLS CONFIGURATION
# ============================================================

mqtt_client.tls_set(
    ca_certs=CA_PATH,
    certfile=CERT_PATH,
    keyfile=KEY_PATH,
    tls_version=ssl.PROTOCOL_TLSv1_2
)


# ============================================================
# CALLBACKS
# ============================================================

mqtt_client.on_connect = on_connect
mqtt_client.on_disconnect = on_disconnect


# ============================================================
# MQTT AUTOMATIC RECONNECT DELAY
# ============================================================

mqtt_client.reconnect_delay_set(
    min_delay=2,
    max_delay=30
)


# ============================================================
# DATABASE
# ============================================================

def open_database():

    connection = sqlite3.connect(
        DB_PATH,
        timeout=10,
        check_same_thread=False
    )

    connection.row_factory = sqlite3.Row

    connection.execute(
        "PRAGMA busy_timeout=10000"
    )

    connection.execute(
        "PRAGMA journal_mode=WAL"
    )

    return connection


conn = open_database()

cursor = conn.cursor()


# ============================================================
# CONNECT TO AWS
# ============================================================

def connect_to_aws():

    global mqtt_connected

    while not mqtt_connected:

        try:

            print(
                "🔌 Connecting to AWS IoT Core..."
            )

            mqtt_client.connect(
                MQTT_ENDPOINT,
                MQTT_PORT,
                keepalive=60
            )

            # Start MQTT network processing
            mqtt_client.loop_start()

            # Wait for on_connect callback
            for _ in range(20):

                if mqtt_connected:
                    return True

                time.sleep(0.25)

            print(
                "⚠️ AWS connection timeout. Retrying..."
            )

        except Exception as e:

            mqtt_connected = False

            print(
                f"❌ AWS connection error: {e}"
            )

            time.sleep(3)

    return True


# ============================================================
# CREATE COMPLETE AWS PAYLOAD
# ============================================================

def create_payload(row):

    payload = {

        # ----------------------------------------------------
        # DATABASE ID
        # ----------------------------------------------------

        "id": row["id"],

        # ----------------------------------------------------
        # DEVICE
        # ----------------------------------------------------

        "device_id": row["device_id"],

        # ----------------------------------------------------
        # PRESSURE RAW VALUES
        # ----------------------------------------------------

        "BP_raw": row["BP_raw"],

        "FP_raw": row["FP_raw"],

        "CR_raw": row["CR_raw"],

        "BC_raw": row["BC_raw"],

        # ----------------------------------------------------
        # TIMESTAMP
        # ----------------------------------------------------

        "timestamp": row["timestamp"],

        # ----------------------------------------------------
        # GSM
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
        # GNSS
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
# UPLOAD ONE DATABASE ROW
# ============================================================

def upload_row(row):

    global mqtt_connected

    row_id = row["id"]

    # --------------------------------------------------------
    # CHECK MQTT CONNECTION
    # --------------------------------------------------------

    if not mqtt_connected:

        print(
            "⚠️ AWS MQTT is disconnected."
        )

        print(
            "⏳ Waiting for AWS connection..."
        )

        return False


    # --------------------------------------------------------
    # CREATE PAYLOAD
    # --------------------------------------------------------

    payload = create_payload(row)

    payload_json = json.dumps(
        payload,
        default=str
    )


    # ========================================================
    # PRINT DATA TO BE UPLOADED
    # ========================================================

    print()
    print("--------------------------------------------------")

    print(
        f"📥 Local DB ID       : {row['id']}"
    )

    print(
        f"device_id={row['device_id']}"
    )

    print(
        f"BP_raw={row['BP_raw']}, "
        f"FP_raw={row['FP_raw']}, "
        f"CR_raw={row['CR_raw']}, "
        f"BC_raw={row['BC_raw']}"
    )

    print(
        f"GNSS={row['gnss_status']}, "
        f"LAT={row['latitude']}, "
        f"LON={row['longitude']}, "
        f"ALT={row['altitude_m']}, "
        f"SAT={row['satellites']}"
    )

    print(
        f"GSM={row['gsm_status']}, "
        f"RSSI={row['signal_strength']}, "
        f"dBm={row['signal_dbm']}, "
        f"Network={row['network_status']}, "
        f"Operator={row['operator']}, "
        f"Latency={row['latency_ms']} ms"
    )

    print(
        f"Timestamp={row['timestamp']}"
    )


    # ========================================================
    # SEND TO AWS
    # ========================================================

    print()
    print("📤 AWS Sent:")

    print(
        json.dumps(
            payload,
            indent=2,
            default=str
        )
    )


    try:

        result = mqtt_client.publish(
            TOPIC,
            payload_json,
            qos=1
        )

        # ----------------------------------------------------
        # CHECK MQTT RESULT
        # ----------------------------------------------------

        if result.rc != mqtt.MQTT_ERR_SUCCESS:

            print(
                f"❌ MQTT publish failed | "
                f"ID={row_id} | rc={result.rc}"
            )

            mqtt_connected = False

            return False


        # ----------------------------------------------------
        # WAIT FOR QoS 1 CONFIRMATION
        # ----------------------------------------------------

        result.wait_for_publish(
            timeout=10
        )


        if not result.is_published():

            print(
                f"❌ AWS publish not confirmed | "
                f"ID={row_id}"
            )

            return False


        # ====================================================
        # AWS SUCCESS
        # ====================================================

        print(
            f"✅ AWS upload confirmed | ID={row_id}"
        )


        # ====================================================
        # UPDATE SQLITE ONLY AFTER SUCCESS
        # ====================================================

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
            f"✅ SQLite updated | "
            f"ID={row_id} | uploaded=1"
        )

        print("--------------------------------------------------")
        print()

        return True


    except Exception as e:

        print()
        print(
            f"❌ AWS upload error | "
            f"ID={row_id}"
        )

        print(
            f"   Error: {e}"
        )

        print(
            "⏳ Record remains uploaded=0"
        )

        return False


# ============================================================
# MAIN LOOP
# ============================================================

try:

    # --------------------------------------------------------
    # INITIAL AWS CONNECTION
    # --------------------------------------------------------

    connect_to_aws()


    print(
        "🚀 upload1.py started..."
    )

    print(
        "📂 Monitoring SQLite for uploaded=0 records..."
    )

    print()


    # ========================================================
    # CONTINUOUS LOOP
    # ========================================================

    while True:

        # ----------------------------------------------------
        # IF MQTT DISCONNECTED
        # ----------------------------------------------------

        if not mqtt_connected:

            print(
                "⚠️ AWS connection lost."
            )

            print(
                "⏳ Waiting for MQTT automatic reconnect..."
            )

            time.sleep(3)

            continue


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
        # NO OFFLINE RECORD
        # ----------------------------------------------------

        if row is None:

            time.sleep(0.5)

            continue


        # ----------------------------------------------------
        # UPLOAD RECORD
        # ----------------------------------------------------

        success = upload_row(row)


        # ----------------------------------------------------
        # FAILED
        # ----------------------------------------------------

        if not success:

            print(
                f"⏳ Retry ID={row['id']} after 3 seconds..."
            )

            time.sleep(3)


# ============================================================
# CTRL+C
# ============================================================

except KeyboardInterrupt:

    print()
    print(
        "🛑 upload1.py stopped by user."
    )


# ============================================================
# CLEANUP
# ============================================================

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
        "🔴 AWS uploader closed."
    )
