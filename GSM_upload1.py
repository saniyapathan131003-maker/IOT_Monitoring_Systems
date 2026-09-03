#!/usr/bin/env python3

import os
import time
import sqlite3
import json
import ssl
import threading
import paho.mqtt.client as mqtt


# ============================================================
# PATH CONFIGURATION
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

MQTT_ENDPOINT = "a1vddjuckiz90j-ats.iot.ap-south-1.amazonaws.com"

CLIENT_ID = "Raspberrypi_4A"

TOPIC = f"{CLIENT_ID}/data"

MQTT_PORT = 8883


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

def on_connect(client, userdata, flags, reason_code, properties=None):

    global mqtt_connected

    with mqtt_lock:

        # Paho MQTT 2.x ReasonCode
        if hasattr(reason_code, "is_failure"):

            if reason_code.is_failure:
                mqtt_connected = False

                print(
                    f"❌ AWS MQTT connection failed | "
                    f"Reason={reason_code}"
                )

                return

        # Paho MQTT 3.x compatibility
        elif reason_code != 0:

            mqtt_connected = False

            print(
                f"❌ AWS MQTT connection failed | "
                f"Code={reason_code}"
            )

            return

        mqtt_connected = True

    print()
    print("=" * 60)
    print("✅ Connected to AWS IoT Core")
    print(f"📡 Endpoint : {MQTT_ENDPOINT}")
    print(f"📤 Topic    : {TOPIC}")
    print(f"🆔 Client ID: {CLIENT_ID}")
    print("=" * 60)
    print()


# ============================================================
# MQTT DISCONNECT CALLBACK
# ============================================================

def on_disconnect(client, userdata, disconnect_flags, reason_code, properties=None):

    global mqtt_connected

    with mqtt_lock:
        mqtt_connected = False

    print(
        f"⚠️ AWS MQTT disconnected | "
        f"Reason={reason_code}"
    )


# ============================================================
# CREATE MQTT CLIENT
# ============================================================

mqtt_client = mqtt.Client(
    mqtt.CallbackAPIVersion.VERSION2,
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
# START MQTT NETWORK LOOP
# ============================================================

print()
print("=" * 60)
print("🚀 AWS OFFLINE UPLOADER")
print("=" * 60)
print("🔄 Starting MQTT network loop...")
print("=" * 60)

mqtt_client.loop_start()


# ============================================================
# CONNECT TO AWS
# ============================================================

def connect_aws():

    global mqtt_connected

    while True:

        with mqtt_lock:
            if mqtt_connected:
                return True

        try:

            print("🔌 Connecting to AWS IoT Core...")

            mqtt_client.connect(
                MQTT_ENDPOINT,
                port=MQTT_PORT,
                keepalive=60
            )

            # Give callback time to execute
            for _ in range(30):

                with mqtt_lock:
                    if mqtt_connected:
                        return True

                time.sleep(0.1)

            print("⚠️ AWS connection timeout.")

        except Exception as e:

            with mqtt_lock:
                mqtt_connected = False

            print(
                f"❌ AWS connection failed: {e}"
            )

        print("⏳ Retrying AWS connection in 2 seconds...")
        time.sleep(2)


# ============================================================
# CHECK / RECONNECT
# ============================================================

def ensure_connection():

    global mqtt_connected

    with mqtt_lock:
        connected = mqtt_connected

    if connected:
        return True

    print()
    print("⚠️ AWS MQTT is disconnected.")
    print("🔄 Reconnecting...")

    try:

        mqtt_client.reconnect()

        for _ in range(30):

            with mqtt_lock:
                if mqtt_connected:
                    print("✅ AWS MQTT reconnected.")
                    return True

            time.sleep(0.1)

    except Exception as e:

        print(
            f"❌ MQTT reconnect failed: {e}"
        )

    return connect_aws()


# ============================================================
# SAFE DATABASE VALUE
# ============================================================

def get_value(row, column):

    try:
        return row[column]
    except (KeyError, IndexError):
        return None


# ============================================================
# CREATE COMPLETE AWS PAYLOAD
# ============================================================

def create_payload(row):

    payload = {

        # ---------------- BASIC ----------------
        "id": get_value(row, "id"),

        "device_id": get_value(
            row,
            "device_id"
        ),

        "timestamp": get_value(
            row,
            "timestamp"
        ),

        # ---------------- PRESSURE ----------------
        "BP_raw": get_value(
            row,
            "BP_raw"
        ),

        "FP_raw": get_value(
            row,
            "FP_raw"
        ),

        "CR_raw": get_value(
            row,
            "CR_raw"
        ),

        "BC_raw": get_value(
            row,
            "BC_raw"
        ),

        # ---------------- GSM ----------------
        "gsm_status": get_value(
            row,
            "gsm_status"
        ),

        "sim_status": get_value(
            row,
            "sim_status"
        ),

        "sim_iccid": get_value(
            row,
            "sim_iccid"
        ),

        "mobile_number": get_value(
            row,
            "mobile_number"
        ),

        "signal_strength": get_value(
            row,
            "signal_strength"
        ),

        "signal_dbm": get_value(
            row,
            "signal_dbm"
        ),

        "network_status": get_value(
            row,
            "network_status"
        ),

        "operator": get_value(
            row,
            "operator"
        ),

        "latency_ms": get_value(
            row,
            "latency_ms"
        ),

        # ---------------- GNSS ----------------
        "gnss_status": get_value(
            row,
            "gnss_status"
        ),

        "latitude": get_value(
            row,
            "latitude"
        ),

        "longitude": get_value(
            row,
            "longitude"
        ),

        "altitude_m": get_value(
            row,
            "altitude_m"
        ),

        "satellites": get_value(
            row,
            "satellites"
        ),

        "gps_utc": get_value(
            row,
            "gps_utc"
        )
    }

    return payload


# ============================================================
# PRINT LOCAL DATABASE DATA
# ============================================================

def print_local_data(row):

    print(
        f"📥 Local DB row | "
        f"ID={row['id']} | "
        f"device_id={row['device_id']} | "
        f"BP_raw={row['BP_raw']} | "
        f"FP_raw={row['FP_raw']} | "
        f"CR_raw={row['CR_raw']} | "
        f"BC_raw={row['BC_raw']} | "
        f"GNSS={row['gnss_status']} | "
        f"LAT={row['latitude']} | "
        f"LON={row['longitude']} | "
        f"SAT={row['satellites']} | "
        f"GSM={row['gsm_status']} | "
        f"RSSI={row['signal_strength']} | "
        f"dBm={row['signal_dbm']} | "
        f"Network={row['network_status']} | "
        f"Latency={row['latency_ms']} ms | "
        f"Timestamp={row['timestamp']}"
    )


# ============================================================
# PUBLISH ONE ROW
# ============================================================

def publish_row(row):

    global mqtt_connected

    # --------------------------------------------------------
    # Make sure AWS is connected
    # --------------------------------------------------------

    if not ensure_connection():

        print(
            f"❌ Cannot upload ID={row['id']} "
            f"because AWS is disconnected."
        )

        return False


    # --------------------------------------------------------
    # Create JSON payload
    # --------------------------------------------------------

    payload = create_payload(row)

    payload_json = json.dumps(
        payload,
        separators=(",", ":"),
        ensure_ascii=False
    )


    # --------------------------------------------------------
    # Print local data
    # --------------------------------------------------------

    print_local_data(row)

    print()
    print("📤 AWS SENT PAYLOAD:")
    print(
        json.dumps(
            payload,
            indent=2,
            ensure_ascii=False
        )
    )


    # --------------------------------------------------------
    # Publish QoS 1
    # --------------------------------------------------------

    try:

        with mqtt_lock:

            if not mqtt_connected:

                print(
                    "⚠️ AWS disconnected before publish."
                )

                return False

            result = mqtt_client.publish(
                TOPIC,
                payload_json,
                qos=1
            )


        # ----------------------------------------------------
        # Check publish request
        # ----------------------------------------------------

        if result.rc != mqtt.MQTT_ERR_SUCCESS:

            print(
                f"❌ MQTT publish failed | "
                f"RC={result.rc}"
            )

            return False


        # ----------------------------------------------------
        # Wait until MQTT packet is actually sent
        # ----------------------------------------------------

        try:

            result.wait_for_publish(
                timeout=10
            )

        except Exception as e:

            print(
                f"❌ Publish wait error: {e}"
            )

            return False


        # ----------------------------------------------------
        # Confirm publish
        # ----------------------------------------------------

        if not result.is_published():

            print(
                f"❌ AWS publish not confirmed "
                f"for ID={row['id']}"
            )

            return False


        # ----------------------------------------------------
        # Mark SQLite row uploaded
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
        # Verify database update
        # ----------------------------------------------------

        cursor.execute(
            """
            SELECT uploaded
            FROM brake_pressure_log
            WHERE id = ?
            """,
            (row["id"],)
        )

        check = cursor.fetchone()


        if check and check["uploaded"] == 1:

            print()
            print(
                f"✅ AWS UPLOAD SUCCESS | "
                f"ID={row['id']} | "
                f"uploaded=1"
            )

            print("-" * 60)
            print()

            return True


        print(
            f"⚠️ AWS publish succeeded but "
            f"database update could not be verified "
            f"for ID={row['id']}"
        )

        return False


    except Exception as e:

        print()
        print(
            f"❌ AWS publish error "
            f"for ID={row['id']}: {e}"
        )

        with mqtt_lock:
            mqtt_connected = False

        return False


# ============================================================
# MAIN UPLOADER LOOP
# ============================================================

def main():

    print()
    print("=" * 60)
    print("🚀 AWS OFFLINE UPLOADER STARTED")
    print("=" * 60)
    print(f"📂 Database : {DB_PATH}")
    print(f"📡 Endpoint : {MQTT_ENDPOINT}")
    print(f"📤 Topic    : {TOPIC}")
    print(f"🆔 Client ID: {CLIENT_ID}")
    print("=" * 60)
    print()


    # --------------------------------------------------------
    # Initial AWS connection
    # --------------------------------------------------------

    connect_aws()


    # --------------------------------------------------------
    # Continuous upload loop
    # --------------------------------------------------------

    while True:

        try:

            # -----------------------------------------------
            # Get oldest unuploaded row
            # -----------------------------------------------

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


            # -----------------------------------------------
            # No pending data
            # -----------------------------------------------

            if row is None:

                time.sleep(0.1)
                continue


            # -----------------------------------------------
            # Publish row
            # -----------------------------------------------

            success = publish_row(row)


            # -----------------------------------------------
            # Success
            # -----------------------------------------------

            if success:

                # Immediately check next DB row
                time.sleep(0.01)


            # -----------------------------------------------
            # Failed
            # -----------------------------------------------

            else:

                print(
                    f"⏳ ID={row['id']} "
                    f"will remain uploaded=0."
                )

                print(
                    "🔄 Retrying after 2 seconds..."
                )

                time.sleep(2)


        except sqlite3.Error as e:

            print(
                f"❌ SQLite error: {e}"
            )

            time.sleep(1)


        except KeyboardInterrupt:

            print()
            print(
                "🛑 AWS uploader stopped by user."
            )

            break


        except Exception as e:

            print(
                f"❌ Unexpected uploader error: {e}"
            )

            time.sleep(1)


# ============================================================
# START PROGRAM
# ============================================================

if __name__ == "__main__":

    try:

        main()

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
            "👋 AWS uploader exited."
        )