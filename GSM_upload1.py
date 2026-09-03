
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

KEEPALIVE = 60


# ============================================================
# MQTT STATUS
# ============================================================

mqtt_connected = False

mqtt_lock = threading.Lock()


# ============================================================
# MQTT CONNECT CALLBACK
# ============================================================

def on_connect(
    client,
    userdata,
    flags,
    reason_code,
    properties=None
):

    global mqtt_connected

    # --------------------------------------------------------
    # Paho MQTT 2.x
    # --------------------------------------------------------

    if reason_code.is_failure:

        with mqtt_lock:
            mqtt_connected = False

        print(
            f"❌ AWS MQTT connection failed | "
            f"Reason={reason_code}"
        )

        return


    with mqtt_lock:
        mqtt_connected = True

    print()
    print("======================================================")
    print("✅ Connected to AWS IoT Core")
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

    reason = str(reason_code)

    # --------------------------------------------------------
    # Normal disconnect
    # --------------------------------------------------------

    if reason == "Normal disconnection":

        print(
            "🔌 AWS MQTT disconnected normally."
        )

    else:

        print()
        print(
            f"⚠️ AWS MQTT disconnected | Reason={reason}"
        )

        print(
            "🔄 Reconnection will be attempted..."
        )

        print()


# ============================================================
# CHECK MQTT STATUS
# ============================================================

def is_connected():

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
# MQTT AUTOMATIC RECONNECT DELAY
# ============================================================

mqtt_client.reconnect_delay_set(
    min_delay=2,
    max_delay=10
)


# ============================================================
# SQLITE
# ============================================================

conn = sqlite3.connect(
    DB_PATH,
    timeout=10,
    check_same_thread=False
)

conn.row_factory = sqlite3.Row

cursor = conn.cursor()


# ============================================================
# SQLITE PERFORMANCE
# ============================================================

cursor.execute(
    "PRAGMA journal_mode=WAL"
)

cursor.execute(
    "PRAGMA busy_timeout=10000"
)

conn.commit()


# ============================================================
# CHECK DATABASE TABLE
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

    print(
        "❌ brake_pressure_log table not found."
    )

    conn.close()

    raise SystemExit(1)


# ============================================================
# CREATE COMPLETE AWS PAYLOAD
# ============================================================

def create_payload(row):

    return {

        # ----------------------------------------------------
        # DATABASE ID
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
# PRINT DATA FROM SQLITE
# ============================================================

def print_db_data(row):

    print()
    print(
        "📥 SQLITE DATA"
    )

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


# ============================================================
# GET ONE UNSENT RECORD
# ============================================================

def get_pending_row():

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
# MARK ROW AS UPLOADED
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

        conn.commit()

        return True

    except sqlite3.Error as e:

        print(
            f"❌ SQLite update error | ID={row_id} | {e}"
        )

        return False


# ============================================================
# CONNECT TO AWS
# ============================================================

def connect_aws():

    while not is_connected():

        try:

            print(
                "🔌 Connecting to AWS IoT Core..."
            )

            # ------------------------------------------------
            # Start background MQTT loop only once
            # ------------------------------------------------

            mqtt_client.loop_start()

            # ------------------------------------------------
            # Synchronous initial connection
            # ------------------------------------------------

            result = mqtt_client.connect(
                MQTT_ENDPOINT,
                port=MQTT_PORT,
                keepalive=KEEPALIVE
            )

            if result != mqtt.MQTT_ERR_SUCCESS:

                print(
                    f"❌ MQTT connect failed | rc={result}"
                )

                time.sleep(2)

                continue


            # ------------------------------------------------
            # Wait for on_connect callback
            # ------------------------------------------------

            wait_count = 0

            while not is_connected() and wait_count < 20:

                time.sleep(0.1)

                wait_count += 1


            if is_connected():

                return True


            print(
                "❌ AWS connection was not confirmed."
            )

            try:

                mqtt_client.disconnect()

            except Exception:
                pass


            time.sleep(2)


        except Exception as e:

            print(
                f"❌ AWS connect error: {e}"
            )

            time.sleep(2)


    return True


# ============================================================
# RECONNECT WHEN DISCONNECTED
# ============================================================

def reconnect_if_needed():

    if is_connected():

        return True


    print()
    print(
        "⚠️ AWS is disconnected."
    )

    print(
        "🔄 Reconnecting..."
    )


    while not is_connected():

        try:

            result = mqtt_client.reconnect()

            if result == mqtt.MQTT_ERR_SUCCESS:

                # --------------------------------------------
                # Wait for on_connect
                # --------------------------------------------

                for _ in range(20):

                    if is_connected():
                        return True

                    time.sleep(0.1)


            print(
                "❌ Reconnect not confirmed."
            )


        except Exception as e:

            print(
                f"❌ Reconnect failed: {e}"
            )


        time.sleep(2)


    return True


# ============================================================
# PUBLISH ONE DATABASE ROW
# ============================================================

def publish_row(row):

    row_id = row["id"]


    # ========================================================
    # MAKE SURE AWS IS CONNECTED
    # ========================================================

    if not reconnect_if_needed():

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
    # PRINT DATABASE DATA
    # ========================================================

    print_db_data(row)


    print()
    print(
        "📤 Publishing to AWS IoT Core..."
    )


    # ========================================================
    # PUBLISH
    # ========================================================

    try:

        result = mqtt_client.publish(
            TOPIC,
            payload_json,
            qos=1
        )


        # ----------------------------------------------------
        # PUBLISH REQUEST ERROR
        # ----------------------------------------------------

        if result.rc != mqtt.MQTT_ERR_SUCCESS:

            print(
                f"❌ Publish request failed | "
                f"ID={row_id} | rc={result.rc}"
            )

            return False


        # ----------------------------------------------------
        # WAIT FOR AWS MQTT QoS 1 CONFIRMATION
        # ----------------------------------------------------

        result.wait_for_publish(
            timeout=5
        )


        # ----------------------------------------------------
        # CHECK PUBLISHED
        # ----------------------------------------------------

        if not result.is_published():

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
            f"✅ Published successfully | ID={row_id}"
        )


        # ====================================================
        # ONLY NOW SET uploaded=1
        # ====================================================

        if mark_uploaded(row_id):

            print(
                f"✅ SQLite uploaded=1 | ID={row_id}"
            )

            print()

            return True


        print(
            f"⚠️ AWS publish successful but "
            f"SQLite update failed | ID={row_id}"
        )

        return False


    except Exception as e:

        print()
        print(
            f"❌ Publish exception | ID={row_id}"
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
    print("🚀 AWS DATA UPLOADER")
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

    connect_aws()


    print(
        "🚀 Uploader started..."
    )

    print(
        "📂 Monitoring SQLite uploaded=0..."
    )

    print()


    # ========================================================
    # CONTINUOUS LOOP
    # ========================================================

    while True:


        # ====================================================
        # AWS CONNECTION CHECK
        # ====================================================

        if not is_connected():

            reconnect_if_needed()

            continue


        # ====================================================
        # GET ONE ROW
        # ====================================================

        row = get_pending_row()


        # ====================================================
        # NO DATA
        # ====================================================

        if row is None:

            # -----------------------------------------------
            # 100 ms database polling
            # -----------------------------------------------

            time.sleep(0.1)

            continue


        # ====================================================
        # PUBLISH
        # ====================================================

        success = publish_row(row)


        # ====================================================
        # SUCCESS
        # ====================================================

        if success:

            # -----------------------------------------------
            # Immediately fetch next row
            # -----------------------------------------------

            continue


        # ====================================================
        # FAILURE
        # ====================================================

        print()
        print(
            f"⏳ ID={row['id']} remains uploaded=0"
        )

        print(
            "🔄 Retrying..."
        )

        time.sleep(1)


# ============================================================
# CTRL+C
# ============================================================

except KeyboardInterrupt:

    print()
    print(
        "🛑 Stopping AWS uploader..."
    )


# ============================================================
# CLEANUP
# ============================================================

finally:

    try:

        mqtt_client.disconnect()

    except Exception:
        pass


    try:

        mqtt_client.loop_stop()

    except Exception:
        pass


    try:

        conn.close()

    except Exception:
        pass


    print(
        "✅ AWS uploader stopped."
    )
