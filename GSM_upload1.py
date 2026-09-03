```python
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
# AWS IoT
# ============================================================

MQTT_ENDPOINT = "a1vddjuckiz90j-ats.iot.ap-south-1.amazonaws.com"

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
# MQTT CONNECT CALLBACK
# ============================================================

def on_connect(client, userdata, flags, reason_code, properties=None):

    global mqtt_connected

    # MQTT v2 ReasonCode
    if reason_code.is_failure:

        with mqtt_lock:
            mqtt_connected = False

        connection_event.clear()

        print()
        print(
            f"❌ AWS connection failed | Reason={reason_code}"
        )
        print()

        return


    # --------------------------------------------------------
    # SUCCESS
    # --------------------------------------------------------

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


# ============================================================
# MQTT DISCONNECT CALLBACK
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

    # --------------------------------------------------------
    # DO NOT CONVERT ReasonCode USING int()
    # --------------------------------------------------------

    reason = str(reason_code)

    if reason == "Normal disconnection":

        print()
        print(
            "🔌 AWS MQTT disconnected normally."
        )
        print()

    else:

        print()
        print(
            f"⚠️ AWS MQTT connection lost | Reason={reason_code}"
        )

        print(
            "🔄 Automatic reconnect is active..."
        )

        print()


# ============================================================
# MQTT CONNECTION STATUS
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
    min_delay=2,
    max_delay=15
)


# ============================================================
# SQLITE
# ============================================================

db = sqlite3.connect(
    DB_PATH,
    timeout=10,
    check_same_thread=False
)

db.row_factory = sqlite3.Row

cursor = db.cursor()

# ------------------------------------------------------------
# WAL allows capture script and uploader to work together
# ------------------------------------------------------------

cursor.execute(
    "PRAGMA journal_mode=WAL"
)

cursor.execute(
    "PRAGMA busy_timeout=10000"
)

db.commit()


# ============================================================
# CHECK REQUIRED TABLE
# ============================================================

cursor.execute(
    """
    SELECT name
    FROM sqlite_master
    WHERE type='table'
    AND name='brake_pressure_log'
    """
)

if cursor.fetchone() is None:

    print()
    print(
        "❌ ERROR: brake_pressure_log table not found."
    )
    print(
        f"Database: {DB_PATH}"
    )
    print()

    db.close()

    raise SystemExit(1)


# ============================================================
# CREATE AWS PAYLOAD
# ============================================================

def create_payload(row):

    payload = {

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
        # TIME
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
# GET OLDEST UNSENT RECORD
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
# MARK RECORD UPLOADED
# ============================================================

def mark_uploaded(row_id):

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

        return True

    except sqlite3.Error as e:

        print(
            f"❌ SQLite update error | ID={row_id} | {e}"
        )

        return False


# ============================================================
# WAIT FOR AWS
# ============================================================

def wait_for_connection():

    while not is_mqtt_connected():

        print(
            "⏳ Waiting for AWS connection..."
        )

        # ----------------------------------------------------
        # Paho background loop handles reconnect automatically
        # ----------------------------------------------------

        connection_event.wait(
            timeout=5
        )


# ============================================================
# PUBLISH ONE RECORD
# ============================================================

def publish_record(row):

    row_id = row["id"]


    # ========================================================
    # CHECK CONNECTION
    # ========================================================

    if not is_mqtt_connected():

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
    # DISPLAY DATA
    # ========================================================

    print()
    print("------------------------------------------------------")

    print(
        f"📥 DB ID={row_id} | "
        f"Device={row['device_id']}"
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
        f"SAT={row['satellites']}"
    )

    print(
        f"GSM={row['gsm_status']}, "
        f"RSSI={row['signal_strength']}, "
        f"dBm={row['signal_dbm']}, "
        f"Network={row['network_status']}"
    )

    print(
        f"Timestamp={row['timestamp']}"
    )

    print(
        "📤 Publishing to AWS..."
    )


    # ========================================================
    # MQTT PUBLISH
    # ========================================================

    try:

        result = mqtt_client.publish(
            TOPIC,
            payload_json,
            qos=1
        )


        # ----------------------------------------------------
        # PUBLISH REQUEST FAILED
        # ----------------------------------------------------

        if result.rc != mqtt.MQTT_ERR_SUCCESS:

            print(
                f"❌ Publish request failed | "
                f"ID={row_id} | rc={result.rc}"
            )

            return False


        # ----------------------------------------------------
        # WAIT FOR QoS 1 PUBACK
        # ----------------------------------------------------

        result.wait_for_publish(
            timeout=10
        )


        # ----------------------------------------------------
        # CONFIRM PUBLISHED
        # ----------------------------------------------------

        if not result.is_published():

            print(
                f"❌ AWS publish not confirmed | "
                f"ID={row_id}"
            )

            return False


        # ====================================================
        # SUCCESS
        # ====================================================

        print()
        print("======================================================")
        print("📤 AWS SENT PAYLOAD")
        print("======================================================")

        print(payload_json)

        print("======================================================")


        print(
            f"✅ AWS PUBLISH SUCCESS | ID={row_id}"
        )


        # ====================================================
        # UPDATE SQLITE
        # ====================================================

        if mark_uploaded(row_id):

            print(
                f"✅ DB UPDATED | ID={row_id} | uploaded=1"
            )

            print()

            return True


        # ----------------------------------------------------
        # AWS succeeded but SQLite update failed
        # ----------------------------------------------------

        print(
            f"⚠️ AWS received ID={row_id}, "
            f"but SQLite update failed."
        )

        return False


    except Exception as e:

        print()
        print(
            f"❌ AWS publish error | ID={row_id}"
        )

        print(
            f"   {e}"
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
    print(f"📂 Database : {DB_PATH}")
    print(f"📡 Endpoint : {MQTT_ENDPOINT}")
    print(f"📤 Topic    : {TOPIC}")
    print(f"🆔 Client ID: {CLIENT_ID}")
    print("======================================================")
    print()


    # ========================================================
    # START MQTT NETWORK THREAD ONCE
    # ========================================================

    print(
        "🔄 Starting MQTT network loop..."
    )

    mqtt_client.loop_start()


    # ========================================================
    # START ASYNC CONNECTION
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
    # WAIT FOR FIRST CONNECTION
    # ========================================================

    wait_for_connection()


    print()
    print(
        "🚀 AWS OFFLINE UPLOADER STARTED"
    )

    print(
        "📂 Reading uploaded=0 records..."
    )

    print()


    # ========================================================
    # CONTINUOUS DATABASE UPLOAD LOOP
    # ========================================================

    while True:


        # ====================================================
        # AWS DISCONNECTED
        # ====================================================

        if not is_mqtt_connected():

            print(
                "⚠️ AWS disconnected."
            )

            wait_for_connection()

            continue


        # ====================================================
        # GET ONE RECORD
        # ====================================================

        row = get_pending_record()


        # ====================================================
        # NO PENDING DATA
        # ====================================================

        if row is None:

            # ------------------------------------------------
            # Check DB frequently for new records
            # ------------------------------------------------

            time.sleep(0.2)

            continue


        # ====================================================
        # PUBLISH
        # ====================================================

        success = publish_record(row)


        # ====================================================
        # FAILED
        # ========================================================

        if not success:

            print()
            print(
                f"⏳ ID={row['id']} NOT uploaded."
            )

            print(
                "⏳ Keeping uploaded=0."
            )

            print(
                "🔄 Retrying after 2 seconds..."
            )

            time.sleep(2)

        else:

            # ------------------------------------------------
            # Immediately check next row
            # ------------------------------------------------

            time.sleep(0.01)


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
        "🔌 Closing AWS connection..."
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
        "✅ AWS uploader stopped."
    )
```
