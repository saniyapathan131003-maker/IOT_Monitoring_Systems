
#!/usr/bin/env python3

import os
import time
import sqlite3
import json
import ssl
import threading
import paho.mqtt.client as mqtt


# ============================================================
# AWS OFFLINE UPLOADER
# ============================================================


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
# AWS CERTIFICATES
# ============================================================

CA_PATH = os.path.join(
    BASE_DIR,
    "certs_3",
    "AmazonRootCA1.pem"
)

CERT_PATH = os.path.join(
    BASE_DIR,
    "certs_3",
    "certificate.pem.crt"
)

KEY_PATH = os.path.join(
    BASE_DIR,
    "certs_3",
    "private.pem.key"
)


# ============================================================
# AWS MQTT CONFIGURATION
# ============================================================

MQTT_ENDPOINT = "a1vddjuckiz90j-ats.iot.ap-south-1.amazonaws.com"

MQTT_PORT = 8883

# KEEP SAME FOR ALL
CLIENT_ID = "Raspberrypi_4"

# KEEP SAME FOR ALL
TOPIC = f"{CLIENT_ID}/data/2"


# ============================================================
# DATABASE CONNECTION
# ============================================================

conn = sqlite3.connect(
    DB_PATH,
    check_same_thread=False,
    timeout=30
)

conn.row_factory = sqlite3.Row

cursor = conn.cursor()

cursor.execute("PRAGMA journal_mode=WAL")
cursor.execute("PRAGMA busy_timeout=30000")

conn.commit()


# ============================================================
# MQTT STATUS
# ============================================================

mqtt_connected = False

mqtt_lock = threading.Lock()


# ============================================================
# MQTT CONNECT CALLBACK
# ============================================================

def on_connect(client, userdata, flags, rc):

    global mqtt_connected

    if rc == 0:

        with mqtt_lock:
            mqtt_connected = True

        print("✅ Connected to AWS IoT Core")
        print("🚀 Uploader started...")
        print()

    else:

        with mqtt_lock:
            mqtt_connected = False

        print(
            f"❌ MQTT connection failed with code {rc}"
        )


# ============================================================
# MQTT DISCONNECT CALLBACK
# ============================================================

def on_disconnect(client, userdata, rc):

    global mqtt_connected

    with mqtt_lock:
        mqtt_connected = False

    if rc == 0:

        print(
            "ℹ️ MQTT disconnected normally."
        )

    else:

        print(
            "⚠️ MQTT disconnected. "
            "Will reconnect automatically..."
        )


# ============================================================
# MQTT CLIENT
# ============================================================

mqtt_client = mqtt.Client(
    client_id=CLIENT_ID,
    protocol=mqtt.MQTTv311
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
# STARTUP DISPLAY
# ============================================================

print()

print("=" * 60)

print("🚀 AWS OFFLINE UPLOADER")

print("=" * 60)

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
    "🔄 Starting MQTT network loop..."
)

print("=" * 60)

print()


# ============================================================
# START MQTT NETWORK LOOP
# ============================================================

mqtt_client.loop_start()


# ============================================================
# INITIAL CONNECTION
# ============================================================

while True:

    with mqtt_lock:
        connected = mqtt_connected

    if connected:
        break

    try:

        print(
            "🔌 Connecting to AWS IoT Core..."
        )

        mqtt_client.connect(
            MQTT_ENDPOINT,
            port=MQTT_PORT,
            keepalive=60
        )

        # ----------------------------------------------------
        # Wait for on_connect()
        # ----------------------------------------------------

        for _ in range(30):

            with mqtt_lock:

                if mqtt_connected:
                    break

            time.sleep(0.1)

        with mqtt_lock:
            connected = mqtt_connected

        if connected:
            break

    except Exception as e:

        print(
            f"❌ MQTT connect failed: {e}"
        )

        time.sleep(2)


# ============================================================
# CREATE COMPLETE PAYLOAD
# ============================================================

def create_payload(row):

    return {

        # ----------------------------------------------------
        # BASIC
        # ----------------------------------------------------

        "id": row["id"],

        "device_id": row["device_id"],

        "timestamp": row["timestamp"],


        # ----------------------------------------------------
        # PRESSURE
        # ----------------------------------------------------

        "BP_raw": row["BP_raw"],

        "FP_raw": row["FP_raw"],

        "CR_raw": row["CR_raw"],

        "BC_raw": row["BC_raw"],


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
# WAIT FOR MQTT CONNECTION
# ============================================================

def wait_for_connection():

    global mqtt_connected

    while True:

        with mqtt_lock:
            connected = mqtt_connected

        if connected:

            return True

        print(
            "⚠️ Waiting for MQTT connection "
            "before upload..."
        )

        try:

            mqtt_client.reconnect()

        except Exception as e:

            print(
                f"❌ MQTT reconnect failed: {e}"
            )

        time.sleep(2)


# ============================================================
# PUBLISH ONE DATABASE ROW
# ============================================================

def publish_row(row):

    global mqtt_connected

    # --------------------------------------------------------
    # Make sure MQTT is connected
    # --------------------------------------------------------

    if not wait_for_connection():

        return False


    # --------------------------------------------------------
    # CREATE PAYLOAD
    # --------------------------------------------------------

    payload = create_payload(row)

    payload_json = json.dumps(
        payload,
        ensure_ascii=False
    )


    # --------------------------------------------------------
    # LOCAL DATABASE INFORMATION
    # --------------------------------------------------------

    print()

    print(
        f"device_id={row['device_id']}, "
        f"BP_raw={row['BP_raw']}, "
        f"FP_raw={row['FP_raw']}, "
        f"CR_raw={row['CR_raw']}, "
        f"BC_raw={row['BC_raw']}, "
        f"GNSS={row['gnss_status']}, "
        f"LAT={row['latitude']}, "
        f"LON={row['longitude']}, "
        f"SAT={row['satellites']}, "
        f"GSM={row['gsm_status']}, "
        f"RSSI={row['signal_strength']}, "
        f"dBm={row['signal_dbm']}, "
        f"Network={row['network_status']}, "
        f"Latency={row['latency_ms']} ms, "
        f"Timestamp={row['timestamp']}"
    )


    # --------------------------------------------------------
    # PUBLISH TO AWS IOT
    # --------------------------------------------------------

    try:

        result = mqtt_client.publish(
            TOPIC,
            payload_json,
            qos=1
        )


        # ----------------------------------------------------
        # CHECK IMMEDIATE MQTT ERROR
        # ----------------------------------------------------

        if result.rc != mqtt.MQTT_ERR_SUCCESS:

            print(
                f"❌ MQTT publish failed | "
                f"RC={result.rc}"
            )

            return False


        # ----------------------------------------------------
        # WAIT FOR QoS 1 CONFIRMATION
        # ----------------------------------------------------

        result.wait_for_publish(
            timeout=10
        )


        # ----------------------------------------------------
        # CHECK PUBLISH CONFIRMATION
        # ----------------------------------------------------

        if not result.is_published():

            print(
                f"❌ AWS publish not confirmed "
                f"for ID={row['id']}"
            )

            return False


        # ====================================================
        # DATA SENT SUCCESSFULLY
        # ====================================================

        print()

        print(
            "📤 Data Sent to AWS IoT:"
        )

        print(
            f"device_id={row['device_id']}"
        )

        print(
            f"BP_raw={row['BP_raw']} | "
            f"FP_raw={row['FP_raw']} | "
            f"CR_raw={row['CR_raw']} | "
            f"BC_raw={row['BC_raw']}"
        )

        print(
            f"LAT={row['latitude']} | "
            f"LON={row['longitude']} | "
            f"ALT={row['altitude_m']} m | "
            f"SAT={row['satellites']}"
        )

        print(
            f"GSM={row['gsm_status']} | "
            f"RSSI={row['signal_strength']} | "
            f"dBm={row['signal_dbm']} | "
            f"Network={row['network_status']}"
        )

        print(
            f"GNSS={row['gnss_status']} | "
            f"GPS UTC={row['gps_utc']}"
        )

        print(
            f"Timestamp={row['timestamp']}"
        )


        # ----------------------------------------------------
        # MARK RECORD AS UPLOADED
        # ----------------------------------------------------

        cursor.execute(
            """
            UPDATE brake_pressure_log
            SET uploaded = 1
            WHERE id = ?
            AND uploaded = 0
            """,
            (row["id"],)
        )

        conn.commit()


        # ----------------------------------------------------
        # FINAL SUCCESS MESSAGE
        # ----------------------------------------------------

        print()

        print(
            f"✅ UPLOAD SUCCESS | "
            f"ID={row['id']} | "
            f"uploaded=1"
        )

        print("-" * 60)

        print()

        return True


    except Exception as e:

        print(
            f"❌ Failed to publish "
            f"row id={row['id']}: {e}"
        )

        with mqtt_lock:
            mqtt_connected = False

        return False


# ============================================================
# MAIN LOOP
# ============================================================

try:

    while True:

        # ----------------------------------------------------
        # CHECK AWS CONNECTION
        # ----------------------------------------------------

        with mqtt_lock:
            connected = mqtt_connected


        if not connected:

            print(
                "⚠️ AWS MQTT disconnected."
            )

            try:

                mqtt_client.reconnect()

            except Exception as e:

                print(
                    f"❌ Reconnect failed: {e}"
                )

            time.sleep(2)

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
                ORDER BY timestamp ASC, id ASC
                LIMIT 1
                """
            )

            row = cursor.fetchone()

        except sqlite3.Error as e:

            print(
                f"❌ SQLite error: {e}"
            )

            time.sleep(1)

            continue


        # ----------------------------------------------------
        # NO DATA
        # ----------------------------------------------------

        if row is None:

            time.sleep(0.1)

            continue


        # ----------------------------------------------------
        # PUBLISH RECORD
        # ----------------------------------------------------

        success = publish_row(row)


        # ----------------------------------------------------
        # IF UPLOAD FAILED
        # ----------------------------------------------------

        if not success:

            print(
                f"⏳ Row ID={row['id']} "
                f"remains uploaded=0"
            )

            print(
                "🔄 Will retry..."
            )

            time.sleep(1)

        else:

            # ------------------------------------------------
            # Immediately check next record
            # ------------------------------------------------

            time.sleep(0.01)


# ============================================================
# KEYBOARD INTERRUPT
# ============================================================

except KeyboardInterrupt:

    print()

    print(
        "🛑 AWS uploader stopped by user."
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
        "👋 Uploader exited."
    )
