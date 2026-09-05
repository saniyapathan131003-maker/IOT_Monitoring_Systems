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

CLIENT_ID = "Raspberrypi_4"

TOPIC = f"{CLIENT_ID}/data/2"


# ============================================================
# DATABASE
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

    print(
        "⚠️ MQTT disconnected. "
        "Will reconnect automatically..."
    )


# ============================================================
# MQTT CLIENT
#
# IMPORTANT:
# Use the same style as your original working code.
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
# MQTT NETWORK LOOP
# ============================================================

print()
print("=" * 60)
print("🚀 AWS OFFLINE UPLOADER")
print("=" * 60)
print("🔄 Starting MQTT network loop...")
print("=" * 60)
print()


# Start network thread ONLY ONCE
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

        print("🔌 Connecting to AWS IoT Core...")

        mqtt_client.connect(
            MQTT_ENDPOINT,
            port=MQTT_PORT,
            keepalive=60
        )

        # Wait for on_connect()
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
# GET COMPLETE PAYLOAD
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
    # Make sure connected
    # --------------------------------------------------------

    if not wait_for_connection():
        return False


    # --------------------------------------------------------
    # Create payload
    # --------------------------------------------------------

    payload = create_payload(row)

    payload_json = json.dumps(
        payload,
        ensure_ascii=False
    )


    # --------------------------------------------------------
    # PRINT DATABASE DATA
    # --------------------------------------------------------

    print(
        f"📥 Local DB row: "
        f"device_id={row['device_id']}, "
        f"timestamp={row['timestamp']}, "
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
        f"Latency={row['latency_ms']} ms"
    )


    # --------------------------------------------------------
    # PUBLISH
    # --------------------------------------------------------

    try:

        result = mqtt_client.publish(
            TOPIC,
            payload_json,
            qos=1
        )


        # Check immediate MQTT error
        if result.rc != mqtt.MQTT_ERR_SUCCESS:

            print(
                f"❌ MQTT publish failed | "
                f"RC={result.rc}"
            )

            return False


        # ----------------------------------------------------
        # WAIT FOR QoS 1 PUBLISH
        # ----------------------------------------------------

        result.wait_for_publish(
            timeout=10
        )


        if not result.is_published():

            print(
                f"❌ AWS publish not confirmed "
                f"for ID={row['id']}"
            )

            return False


        # ----------------------------------------------------
        # ONLY NOW MARK UPLOADED
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
        # SUCCESS
        # ----------------------------------------------------

        print()
        print("📤 Sent to AWS IoT:")

        print(
            json.dumps(
                payload,
                indent=2,
                ensure_ascii=False
            )
        )

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
        # Check AWS connection
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
        # PUBLISH
        # ----------------------------------------------------

        success = publish_row(row)


        # ----------------------------------------------------
        # IF FAILED
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

            # Immediately check next row
            time.sleep(0.01)


except KeyboardInterrupt:

    print()
    print("🛑 AWS uploader stopped by user.")


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

    print("👋 Uploader exited.")