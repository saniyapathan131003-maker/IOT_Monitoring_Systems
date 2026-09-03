
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

DB_PATH = os.path.join(
    BASE_DIR,
    "db",
    "new_db.db"
)


# ============================================================
# CERTIFICATE PATHS
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
# MQTT CONFIGURATION
# ============================================================

MQTT_ENDPOINT = "a1vddjuckiz90j-ats.iot.ap-south-1.amazonaws.com"

CLIENT_ID = "Raspberrypi_4A"

TOPIC = f"{CLIENT_ID}/data"


# ============================================================
# DATABASE CONNECTION
# ============================================================

conn = sqlite3.connect(
    DB_PATH,
    check_same_thread=False
)

conn.row_factory = sqlite3.Row

cursor = conn.cursor()


# ============================================================
# MQTT CONNECTION FLAG
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

        print(
            f"❌ MQTT connection failed with code {rc}"
        )


def on_disconnect(client, userdata, rc):

    global mqtt_connected

    mqtt_connected = False

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

mqtt_client.tls_set(
    ca_certs=CA_PATH,
    certfile=CERT_PATH,
    keyfile=KEY_PATH,
    tls_version=ssl.PROTOCOL_TLSv1_2
)

mqtt_client.on_connect = on_connect
mqtt_client.on_disconnect = on_disconnect

# Start MQTT network loop
mqtt_client.loop_start()


# ============================================================
# INITIAL MQTT CONNECTION
# ============================================================

while not mqtt_connected:

    try:

        print("🔄 Connecting to AWS IoT Core...")

        mqtt_client.connect(
            MQTT_ENDPOINT,
            port=8883,
            keepalive=60
        )

    except Exception as e:

        print(
            f"❌ MQTT connect failed: {e}"
        )

        time.sleep(2)

    time.sleep(1)


print("\n🚀 Uploader started...\n")


# ============================================================
# MAIN LOOP
# ============================================================

while True:

    try:

        # ----------------------------------------------------
        # Fetch all offline/unuploaded records
        # ----------------------------------------------------

        cursor.execute(
            """
            SELECT *
            FROM brake_pressure_log
            WHERE uploaded = 0
            ORDER BY timestamp ASC
            """
        )

        rows = cursor.fetchall()


        # ----------------------------------------------------
        # No pending records
        # ----------------------------------------------------

        if not rows:

            time.sleep(0.3)

            continue


        # ----------------------------------------------------
        # Process each offline record
        # ----------------------------------------------------

        for row in rows:

            row_id = row["id"]


            # =================================================
            # CREATE PAYLOAD
            # =================================================

            payload = {
                "device_id": row["device_id"],
                "timestamp": row["timestamp"],

                "BP_raw": row["BP_raw"],
                "FP_raw": row["FP_raw"],
                "CR_raw": row["CR_raw"],
                "BC_raw": row["BC_raw"]
            }


            payload_json = json.dumps(payload)


            # =================================================
            # PRINT LOCAL DATABASE RECORD
            # =================================================

            print(
                f"📥 Local DB row: "
                f"device_id={row['device_id']}, "
                f"timestamp={row['timestamp']}, "
                f"BP_raw={row['BP_raw']}, "
                f"FP_raw={row['FP_raw']}, "
                f"CR_raw={row['CR_raw']}, "
                f"BC_raw={row['BC_raw']}"
            )


            # =================================================
            # WAIT FOR MQTT CONNECTION
            # =================================================

            while not mqtt_connected:

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

                time.sleep(1)


            # =================================================
            # PUBLISH TO AWS IOT
            # =================================================

            try:

                print(
                    f"📤 Uploading row id={row_id}..."
                )


                result = mqtt_client.publish(
                    TOPIC,
                    payload_json,
                    qos=1
                )


                # ------------------------------------------------
                # Check MQTT publish result
                # ------------------------------------------------

                if result.rc == mqtt.MQTT_ERR_SUCCESS:

                    # Wait for MQTT PUBACK.
                    #
                    # This prevents immediately marking the row
                    # uploaded before the MQTT packet is processed.
                    result.wait_for_publish(
                        timeout=10
                    )


                    if result.is_published():

                        # ----------------------------------------
                        # Mark database row as uploaded
                        # ----------------------------------------

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
                            f"✅ Uploaded successfully "
                            f"and marked row id={row_id} "
                            f"as uploaded"
                        )

                        print(
                            f"📤 Sent to AWS IoT: "
                            f"{payload_json}\n"
                        )


                    else:

                        print(
                            f"⚠️ Publish timeout for "
                            f"row id={row_id}. "
                            f"Keeping uploaded=0."
                        )

                        # IMPORTANT:
                        # Do NOT mark the row uploaded.


                else:

                    print(
                        f"❌ MQTT publish failed for "
                        f"row id={row_id}, "
                        f"error code={result.rc}"
                    )

                    # Keep uploaded=0 so it will be
                    # retried later.

                    time.sleep(1)


            except Exception as e:

                print(
                    f"❌ Failed to publish row "
                    f"id={row_id}: {e}"
                )

                # Keep the row in SQLite.
                # It will be retried on the next loop.

                time.sleep(1)


    except sqlite3.Error as e:

        print(
            f"❌ SQLite error: {e}"
        )

        time.sleep(1)


    except Exception as e:

        print(
            f"❌ Unexpected uploader error: {e}"
        )

        time.sleep(1)


    # Small delay before checking SQLite again
    time.sleep(0.1)
