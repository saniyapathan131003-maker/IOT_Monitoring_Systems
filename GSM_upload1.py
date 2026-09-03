
#!/usr/bin/env python3

import os
import time
import json
import ssl
import sqlite3
import threading

import paho.mqtt.client as mqtt


# ============================================================
# CONFIGURATION
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DB_PATH = os.path.join(
    BASE_DIR,
    "db",
    "new_db.db"
)

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
# AWS IoT CONFIGURATION
# ============================================================

MQTT_ENDPOINT = (
    "a1vddjuckiz90j-ats.iot.ap-south-1.amazonaws.com"
)

MQTT_PORT = 8883

CLIENT_ID = "Raspberrypi_4A"

TOPIC = "Raspberrypi_4A/data"

KEEPALIVE = 60


# ============================================================
# MQTT STATUS
# ============================================================

mqtt_connected = False

mqtt_lock = threading.Lock()

connection_event = threading.Event()


# ============================================================
# MQTT CALLBACK - CONNECT
# ============================================================

def on_connect(client, userdata, flags, reason_code, properties=None):

    global mqtt_connected

    # Paho MQTT v2 reason_code
    rc = int(reason_code)

    if rc == 0:

        with mqtt_lock:
            mqtt_connected = True

        connection_event.set()

        print()
        print("======================================================")
        print("✅ AWS IoT Core CONNECTED")
        print("======================================================")
        print(f"📡 Endpoint : {MQTT_ENDPOINT}")
        print(f"📤 Topic    : {TOPIC}")
        print(f"🆔 Client ID: {CLIENT_ID}")
        print("======================================================")
        print()

    else:

        with mqtt_lock:
            mqtt_connected = False

        connection_event.clear()

        print()
        print(
            f"❌ AWS connection failed | rc={rc}"
        )
        print()


# ============================================================
# MQTT CALLBACK - DISCONNECT
# ============================================================

def on_disconnect(
    client,
    userdata,
    disconnect_flags,
    reason_code,
    properties=None
):

    global mqtt_connected

    with mqtt_lock:
        mqtt_connected = False

    connection_event.clear()

    rc = int(reason_code)

    # rc=0 means normal disconnect.
    # Do not print it as an error.
    if rc == 0:

        print()
        print(
            "🔌 AWS MQTT disconnected normally."
        )

    else:

        print()
        print(
            f"⚠️ AWS MQTT connection lost | rc={rc}"
        )

        print(
            "🔄 Paho MQTT will automatically reconnect..."
        )

    print()


# ============================================================
# CHECK CONNECTION
# ============================================================

def is_mqtt_connected():

    with mqtt_lock:
        return mqtt_connected


# ============================================================
# CREATE MQTT CLIENT
# ============================================================

mqtt_client = mqtt.Client(
    callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
    client_id=CLIENT_ID,
    protocol=mqtt.MQTTv311,
    clean_session=True
)


# ============================================================
# TLS
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
# AUTOMATIC RECONNECT
# ============================================================

mqtt_client.reconnect_delay_set(
    min_delay=3,
    max_delay=30
)


# ============================================================
# SQLITE CONNECTION
# ============================================================

def create_database_connection():

    conn = sqlite3.connect(
        DB_PATH,
        timeout=10,
        check_same_thread=False
    )

    conn.row_factory = sqlite3.Row

    conn.execute(
        "PRAGMA journal_mode=WAL"
    )

    conn.execute(
        "PRAGMA busy_timeout=10000"
    )

    return conn


db = create_database_connection()

cursor = db.cursor()


# ============================================================
# CREATE PAYLOAD
# ============================================================

def create_payload(row):

    return {

        # ----------------------------------------------------
        # DATABASE
        # ----------------------------------------------------

        "id": row["id"],

        # ----------------------------------------------------
        # DEVICE
        # ----------------------------------------------------

        "device_id": row["device_id"],

        # ----------------------------------------------------
        # PRESSURE
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


# ============================================================
# GET ONE PENDING RECORD
# ============================================================

def get_pending_record():

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

        return cursor.fetchone()

    except sqlite3.Error as e:

        print(
            f"❌ SQLite read error: {e}"
        )

        return None


# ============================================================
# PRINT LOCAL RECORD
# ============================================================

def print_local_record(row):

    print()
    print("======================================================")
    print(
        f"📥 LOCAL SQLITE RECORD | ID={row['id']}"
    )
    print("======================================================")

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
        f"ALT={row['altitude_m']} m, "
        f"SAT={row['satellites']}"
    )

    print(
        f"GSM={row['gsm_status']}, "
        f"SIM={row['sim_status']}, "
        f"RSSI={row['signal_strength']}, "
        f"dBm={row['signal_dbm']}, "
        f"Network={row['network_status']}, "
        f"Operator={row['operator']}, "
        f"Latency={row['latency_ms']} ms"
    )

    print(
        f"Timestamp={row['timestamp']}"
    )


# ============================================================
# WAIT FOR AWS CONNECTION
# ============================================================

def wait_for_aws():

    while not is_mqtt_connected():

        print(
            "⏳ Waiting for AWS IoT connection..."
        )

        # ----------------------------------------------------
        # Paho is already running in background.
        # It automatically reconnects.
        # ----------------------------------------------------

        connection_event.wait(
            timeout=5
        )

    return True


# ============================================================
# UPLOAD ONE RECORD
# ============================================================

def upload_record(row):

    row_id = row["id"]


    # ========================================================
    # CHECK AWS
    # ========================================================

    if not is_mqtt_connected():

        print()
        print(
            "⚠️ AWS is currently disconnected."
        )

        return False


    # ========================================================
    # CREATE PAYLOAD
    # ========================================================

    payload = create_payload(row)

    payload_json = json.dumps(
        payload,
        default=str,
        separators=(",", ":")
    )


    # ========================================================
    # PRINT LOCAL DATA
    # ========================================================

    print_local_record(row)


    # ========================================================
    # PUBLISH
    # ========================================================

    print()
    print(
        "📤 Publishing data to AWS IoT Core..."
    )


    try:

        result = mqtt_client.publish(
            topic=TOPIC,
            payload=payload_json,
            qos=1
        )


        # ----------------------------------------------------
        # CHECK MQTT PUBLISH REQUEST
        # ----------------------------------------------------

        if result.rc != mqtt.MQTT_ERR_SUCCESS:

            print()
            print(
                f"❌ MQTT publish failed | "
                f"ID={row_id} | rc={result.rc}"
            )

            return False


        # ----------------------------------------------------
        # WAIT FOR QoS 1 CONFIRMATION
        # ----------------------------------------------------

        result.wait_for_publish(
            timeout=10
        )


        # ----------------------------------------------------
        # CHECK CONFIRMATION
        # ----------------------------------------------------

        if not result.is_published():

            print()
            print(
                f"❌ AWS publish not confirmed | "
                f"ID={row_id}"
            )

            return False


        # ====================================================
        # AWS SUCCESS
        # ====================================================

        print()
        print("======================================================")
        print("📤 AWS SENT PAYLOAD")
        print("======================================================")

        print(
            payload_json
        )

        print("======================================================")


        print(
            f"✅ AWS upload confirmed | ID={row_id}"
        )


        # ====================================================
        # UPDATE SQLITE ONLY AFTER AWS SUCCESS
        # ====================================================

        try:

            cursor.execute(
                """
                UPDATE brake_pressure_log
                SET uploaded = 1
                WHERE id = ?
                """,
                (row_id,)
            )

            db.commit()


            print(
                f"✅ SQLite updated | "
                f"ID={row_id} | uploaded=1"
            )

            print()

            return True


        except sqlite3.Error as e:

            print(
                f"❌ SQLite update error | "
                f"ID={row_id} | {e}"
            )

            return False


    except Exception as e:

        print()
        print(
            f"❌ AWS publish exception | "
            f"ID={row_id}"
        )

        print(
            f"   Error: {e}"
        )

        return False


# ============================================================
# MAIN
# ============================================================

try:

    print()
    print("======================================================")
    print("🚀 AWS OFFLINE UPLOADER")
    print("======================================================")
    print(
        f"📂 Database : {DB_PATH}"
    )
    print(
        f"📡 Endpoint : {MQTT_ENDPOINT}"
    )
    print(
        f"📤 Topic    : {TOPIC}"
    )
    print(
        f"🆔 Client ID: {CLIENT_ID}"
    )
    print("======================================================")
    print()


    # ========================================================
    # START MQTT BACKGROUND LOOP
    # ========================================================

    print(
        "🔄 Starting MQTT network loop..."
    )

    mqtt_client.loop_start()


    # ========================================================
    # ASYNCHRONOUS AWS CONNECTION
    # ========================================================

    print(
        "🔌 Connecting to AWS IoT Core..."
    )

    mqtt_client.connect_async(
        MQTT_ENDPOINT,
        MQTT_PORT,
        KEEPALIVE
    )


    # ========================================================
    # WAIT UNTIL CONNECTED
    # ========================================================

    wait_for_aws()


    print()
    print(
        "🚀 AWS offline uploader started."
    )

    print(
        "📂 Monitoring SQLite for uploaded=0..."
    )

    print()


    # ========================================================
    # MAIN UPLOAD LOOP
    # ========================================================

    while True:


        # ====================================================
        # AWS DISCONNECTED
        # ====================================================

        if not is_mqtt_connected():

            print(
                "⚠️ AWS disconnected."
            )

            print(
                "🔄 Waiting for automatic reconnect..."
            )

            wait_for_aws()

            continue


        # ====================================================
        # GET OLDest PENDING ROW
        # ====================================================

        row = get_pending_record()


        # ====================================================
        # NOTHING TO UPLOAD
        # ====================================================

        if row is None:

            time.sleep(1)

            continue


        # ====================================================
        # UPLOAD
        # ====================================================

        success = upload_record(row)


        # ====================================================
        # FAILED
        # ====================================================

        if not success:

            print()
            print(
                f"⏳ Upload failed | ID={row['id']}"
            )

            print(
                "⏳ uploaded remains 0"
            )

            print(
                "🔄 Retrying after 5 seconds..."
            )

            time.sleep(5)


        else:

            # ------------------------------------------------
            # Immediately process next offline record
            # ------------------------------------------------

            time.sleep(0.1)


# ============================================================
# CTRL+C
# ============================================================

except KeyboardInterrupt:

    print()
    print(
        "🛑 Ctrl+C received."
    )


# ============================================================
# CLEANUP
# ============================================================

finally:

    print()
    print(
        "🔌 Stopping AWS MQTT..."
    )

    try:
        mqtt_client.disconnect()
    except Exception:
        pass

    try:
        mqtt_client.loop_stop()
    except Exception:
        pass

    try:
        db.close()
    except Exception:
        pass

    print(
        "✅ AWS offline uploader stopped."
    )
