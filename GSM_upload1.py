
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


# ============================================================
# SQLITE DATABASE
# ============================================================

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

TOPIC = "Raspberrypi_4A/data"


# ============================================================
# GLOBAL MQTT STATUS
# ============================================================

mqtt_connected = False

mqtt_status_lock = threading.Lock()

connection_event = threading.Event()


# ============================================================
# MQTT CALLBACK - CONNECT
# ============================================================

def on_connect(client, userdata, flags, rc):

    global mqtt_connected

    if rc == 0:

        with mqtt_status_lock:
            mqtt_connected = True

        connection_event.set()

        print()
        print("======================================================")
        print("✅ AWS IoT Core CONNECTED")
        print(f"📡 Endpoint : {MQTT_ENDPOINT}")
        print(f"📤 Topic    : {TOPIC}")
        print("======================================================")
        print()

    else:

        with mqtt_status_lock:
            mqtt_connected = False

        connection_event.clear()

        print(
            f"❌ AWS IoT connection failed | rc={rc}"
        )


# ============================================================
# MQTT CALLBACK - DISCONNECT
# ============================================================

def on_disconnect(client, userdata, rc):

    global mqtt_connected

    with mqtt_status_lock:
        mqtt_connected = False

    connection_event.clear()

    print()
    print(
        f"⚠️ AWS MQTT disconnected | rc={rc}"
    )


# ============================================================
# CHECK MQTT CONNECTION
# ============================================================

def is_mqtt_connected():

    with mqtt_status_lock:
        return mqtt_connected


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
# AUTOMATIC RECONNECT DELAY
# ============================================================

mqtt_client.reconnect_delay_set(
    min_delay=5,
    max_delay=30
)


# ============================================================
# DATABASE
# ============================================================

def create_database_connection():

    connection = sqlite3.connect(
        DB_PATH,
        timeout=10,
        check_same_thread=False
    )

    connection.row_factory = sqlite3.Row

    connection.execute(
        "PRAGMA journal_mode=WAL"
    )

    connection.execute(
        "PRAGMA busy_timeout=10000"
    )

    return connection


db = create_database_connection()

cursor = db.cursor()


# ============================================================
# AWS CONNECTION
# ============================================================

def connect_to_aws():

    global mqtt_connected

    while not is_mqtt_connected():

        try:

            print(
                "🔌 Connecting to AWS IoT Core..."
            )

            connection_event.clear()

            # ------------------------------------------------
            # Start MQTT network loop BEFORE connect
            # ------------------------------------------------

            mqtt_client.loop_start()

            result = mqtt_client.connect(
                MQTT_ENDPOINT,
                MQTT_PORT,
                keepalive=60
            )

            if result != mqtt.MQTT_ERR_SUCCESS:

                print(
                    f"❌ MQTT connect returned rc={result}"
                )

                mqtt_client.loop_stop()

                time.sleep(5)

                continue


            # ------------------------------------------------
            # Wait for on_connect callback
            # ------------------------------------------------

            if connection_event.wait(timeout=10):

                return True

            print(
                "❌ AWS connection timeout"
            )

            try:
                mqtt_client.disconnect()
            except Exception:
                pass

            mqtt_client.loop_stop()

            time.sleep(5)


        except Exception as e:

            with mqtt_status_lock:
                mqtt_connected = False

            print(
                f"❌ AWS connection error: {e}"
            )

            try:
                mqtt_client.loop_stop()
            except Exception:
                pass

            time.sleep(5)

    return True


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
# GET OLDEST UNUPLOADED RECORD
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
# PRINT RECORD BEFORE UPLOAD
# ============================================================

def print_record(row):

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
# UPLOAD ONE RECORD
# ============================================================

def upload_record(row):

    row_id = row["id"]


    # ========================================================
    # CHECK AWS CONNECTION
    # ========================================================

    if not is_mqtt_connected():

        print(
            "⚠️ AWS is disconnected."
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
    # SHOW LOCAL DATA
    # ========================================================

    print_record(row)


    # ========================================================
    # PUBLISH TO AWS
    # ========================================================

    print()
    print("📤 Publishing data to AWS IoT Core...")


    try:

        result = mqtt_client.publish(
            topic=TOPIC,
            payload=payload_json,
            qos=1
        )


        # ----------------------------------------------------
        # MQTT INTERNAL ERROR
        # ----------------------------------------------------

        if result.rc != mqtt.MQTT_ERR_SUCCESS:

            print(
                f"❌ MQTT publish request failed | "
                f"ID={row_id} | rc={result.rc}"
            )

            return False


        # ----------------------------------------------------
        # WAIT FOR QoS 1 PUBLISH
        # ----------------------------------------------------

        result.wait_for_publish(
            timeout=10
        )


        # ----------------------------------------------------
        # CHECK PUBLISH CONFIRMATION
        # ----------------------------------------------------

        if not result.is_published():

            print(
                f"❌ AWS publish NOT confirmed | "
                f"ID={row_id}"
            )

            return False


        # ====================================================
        # ONLY AFTER SUCCESSFUL PUBLISH
        # SHOW AWS SENT PAYLOAD
        # ====================================================

        print()
        print("======================================================")
        print("📤 AWS SENT PAYLOAD")
        print("======================================================")

        print(payload_json)

        print("======================================================")


        print(
            f"✅ AWS upload confirmed | ID={row_id}"
        )


        # ====================================================
        # UPDATE SQLITE
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


        except sqlite3.Error as e:

            print(
                f"❌ SQLite update failed | "
                f"ID={row_id} | Error={e}"
            )

            # AWS already received it.
            # Do NOT publish it again automatically.
            return True


        print(
            f"✅ SQLite updated | "
            f"ID={row_id} | uploaded=1"
        )

        print()

        return True


    except Exception as e:

        print()
        print(
            f"❌ AWS upload exception | "
            f"ID={row_id}"
        )

        print(
            f"   Error: {e}"
        )

        print(
            f"⏳ ID={row_id} remains uploaded=0"
        )

        return False


# ============================================================
# MAIN PROGRAM
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
    # INITIAL AWS CONNECTION
    # ========================================================

    connect_to_aws()


    print(
        "🚀 Uploader is now monitoring SQLite..."
    )

    print(
        "⏳ Waiting for uploaded=0 records..."
    )

    print()


    # ========================================================
    # CONTINUOUS LOOP
    # ========================================================

    while True:


        # ====================================================
        # AWS DISCONNECTED
        # ====================================================

        if not is_mqtt_connected():

            print(
                "⚠️ AWS connection lost."
            )

            print(
                "🔄 Waiting for automatic reconnect..."
            )

            time.sleep(3)

            continue


        # ====================================================
        # GET PENDING RECORD
        # ====================================================

        row = get_pending_record()


        # ====================================================
        # NO RECORD
        # ====================================================

        if row is None:

            time.sleep(0.5)

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
                "⏳ Record remains uploaded=0"
            )

            print(
                "🔄 Will retry after 5 seconds..."
            )

            time.sleep(5)

        else:

            # Immediately process next offline record
            time.sleep(0.1)


# ============================================================
# CTRL+C
# ============================================================

except KeyboardInterrupt:

    print()
    print(
        "🛑 Stopping AWS offline uploader..."
    )


# ============================================================
# CLEANUP
# ============================================================

finally:

    print(
        "🔌 Closing AWS MQTT connection..."
    )

    try:
        mqtt_client.loop_stop()
    except Exception:
        pass

    try:
        mqtt_client.disconnect()
    except Exception:
        pass

    try:
        db.close()
    except Exception:
        pass

    print(
        "✅ AWS uploader stopped."
    )