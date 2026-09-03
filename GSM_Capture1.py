#!/usr/bin/env python3

import os
import time
import sqlite3
import serial
import re


# ============================================================
# CONFIGURATION
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DB_PATH = os.path.join(
    BASE_DIR,
    "db",
    "new_db.db"
)

# ---------------- EC200U ----------------

GSM_PORT = "/dev/ttyAMA3"
GSM_BAUDRATE = 115200

# ---------------- PRESSURE ----------------

# KEEPING YOUR EXISTING LOGIC
RAW_THRESHOLD = 326
READ_INTERVAL = 0.1

# ---------------- GSM / GNSS ----------------

GSM_REFRESH_INTERVAL = 30
GNSS_REFRESH_INTERVAL = 5
GNSS_TIMEOUT = 10


# ============================================================
# DATABASE
# ============================================================

conn = sqlite3.connect(
    DB_PATH,
    check_same_thread=False
)

conn.row_factory = sqlite3.Row

cursor = conn.cursor()


# ============================================================
# CREATE TABLE
# ============================================================

cursor.execute("""
CREATE TABLE IF NOT EXISTS brake_pressure_log (

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    device_id TEXT,

    BP_raw INTEGER,
    FP_raw INTEGER,
    CR_raw INTEGER,
    BC_raw INTEGER,

    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,

    uploaded INTEGER DEFAULT 0
)
""")

conn.commit()


# ============================================================
# ADD COLUMNS IF NOT PRESENT
# ============================================================

def add_column_if_missing(column_name, column_type):

    cursor.execute(
        "PRAGMA table_info(brake_pressure_log)"
    )

    columns = [
        row["name"]
        for row in cursor.fetchall()
    ]

    if column_name not in columns:

        cursor.execute(
            f"""
            ALTER TABLE brake_pressure_log
            ADD COLUMN {column_name} {column_type}
            """
        )

        conn.commit()

        print(
            f"✅ Added DB column: {column_name}",
            flush=True
        )


# ---------------- GSM ----------------

add_column_if_missing("gsm_status", "TEXT")
add_column_if_missing("sim_status", "TEXT")
add_column_if_missing("sim_iccid", "TEXT")
add_column_if_missing("mobile_number", "TEXT")
add_column_if_missing("signal_strength", "INTEGER")
add_column_if_missing("signal_dbm", "INTEGER")
add_column_if_missing("network_status", "TEXT")
add_column_if_missing("operator", "TEXT")
add_column_if_missing("latency_ms", "REAL")

# ---------------- GNSS ----------------

add_column_if_missing("gnss_status", "TEXT")
add_column_if_missing("latitude", "REAL")
add_column_if_missing("longitude", "REAL")
add_column_if_missing("altitude_m", "REAL")
add_column_if_missing("satellites", "INTEGER")
add_column_if_missing("gps_utc", "TEXT")


# ============================================================
# DEVICE ID
# ============================================================

cursor.execute(
    "SELECT device_id FROM device_config LIMIT 1"
)

device_row = cursor.fetchone()

if device_row and device_row["device_id"]:

    DEVICE_ID = device_row["device_id"]

else:

    DEVICE_ID = "UNKNOWN"

    print(
        "⚠️ Device ID missing!",
        flush=True
    )


print(
    f"✅ Device ID = {DEVICE_ID}",
    flush=True
)


# ============================================================
# ADS1115
# ============================================================

ADS_AVAILABLE = True

try:

    import board
    import busio

    import adafruit_ads1x15.ads1115 as ADS

    from adafruit_ads1x15.analog_in import AnalogIn


    i2c = busio.I2C(
        board.SCL,
        board.SDA
    )

    ads = ADS.ADS1115(i2c)

    ads.gain = 1


    bp_channel = AnalogIn(
        ads,
        0
    )

    fp_channel = AnalogIn(
        ads,
        1
    )

    cr_channel = AnalogIn(
        ads,
        2
    )

    bc_channel = AnalogIn(
        ads,
        3
    )


    print(
        "✅ ADS1115 initialized",
        flush=True
    )


except Exception as e:

    ADS_AVAILABLE = False

    print(
        f"⚠️ ADS1115 unavailable: {e}",
        flush=True
    )


# ============================================================
# PRESSURE READ
# ============================================================

def read_raw_values():

    if not ADS_AVAILABLE:

        return (
            0,
            0,
            0,
            0
        )


    return (
        bp_channel.value,
        fp_channel.value,
        cr_channel.value,
        bc_channel.value
    )


# ============================================================
# EC200U
# ============================================================

gsm_serial = None


# ============================================================
# GSM DATA CACHE
# ============================================================

gsm_data = {

    "gsm_status": "Disconnected",

    "sim_status": "Unknown",

    "sim_iccid": None,

    "mobile_number": None,

    "signal_strength": None,

    "signal_dbm": None,

    "network_status": "Unknown",

    "operator": None,

    "latency_ms": None
}


# ============================================================
# GNSS DATA CACHE
# ============================================================

gnss_data = {

    "gnss_status": "NO_FIX",

    "latitude": None,

    "longitude": None,

    "altitude_m": None,

    "satellites": None,

    "gps_utc": None
}


# ============================================================
# GPS FIRST FIX EVENT
# ============================================================

# False = GPS has never obtained a valid fix
# True  = GPS has already obtained a valid fix

gnss_fix_available = False


# This becomes True ONLY once when the first valid GPS fix
# is received.

gps_fix_record_pending = False


# ============================================================
# OPEN EC200U
# ============================================================

def open_gsm():

    global gsm_serial

    try:

        gsm_serial = serial.Serial(
            GSM_PORT,
            GSM_BAUDRATE,
            timeout=2
        )

        time.sleep(1)

        print(
            f"✅ EC200U connected on {GSM_PORT}",
            flush=True
        )

        return True


    except Exception as e:

        gsm_serial = None

        print(
            f"❌ EC200U connection failed: {e}",
            flush=True
        )

        return False


# ============================================================
# SEND AT COMMAND
# ============================================================

def send_at(command, timeout=3):

    if gsm_serial is None:

        return ""


    try:

        gsm_serial.reset_input_buffer()

        gsm_serial.write(
            (command + "\r\n").encode()
        )

        gsm_serial.flush()


        response = ""

        start_time = time.time()


        while (
            time.time() - start_time
            < timeout
        ):

            if gsm_serial.in_waiting:

                data = gsm_serial.read(
                    gsm_serial.in_waiting
                )

                response += data.decode(
                    errors="ignore"
                )


            if "\r\nOK\r\n" in response:

                break


            if "ERROR" in response:

                break


            time.sleep(0.05)


        return response


    except Exception as e:

        print(
            f"⚠️ AT command error: {e}",
            flush=True
        )

        return ""


# ============================================================
# MODEM
# ============================================================

def check_modem():

    response = send_at(
        "AT",
        2
    )

    return "OK" in response


# ============================================================
# SIM
# ============================================================

def get_sim_status():

    response = send_at(
        "AT+CPIN?",
        2
    )

    if "+CPIN: READY" in response:

        return "READY"

    return "NOT_READY"


# ============================================================
# ICCID
# ============================================================

def get_iccid():

    response = send_at(
        "AT+QCCID",
        3
    )

    match = re.search(
        r"\+QCCID:\s*([0-9]+)",
        response
    )

    if match:

        return match.group(1)

    return None


# ============================================================
# MOBILE NUMBER
# ============================================================

def get_mobile_number():

    response = send_at(
        "AT+CNUM",
        3
    )

    match = re.search(
        r'\+CNUM:\s*"[^"]*"\s*,\s*"([^"]+)"',
        response
    )

    if match:

        return match.group(1)

    return None


# ============================================================
# SIGNAL
# ============================================================

def get_signal():

    response = send_at(
        "AT+CSQ",
        2
    )

    match = re.search(
        r"\+CSQ:\s*(\d+),(\d+)",
        response
    )

    if not match:

        return None, None


    rssi = int(
        match.group(1)
    )


    if rssi == 99:

        return None, None


    dbm = -113 + (
        2 * rssi
    )


    return rssi, dbm


# ============================================================
# NETWORK
# ============================================================

def get_network_status():

    response = send_at(
        "AT+CREG?",
        2
    )

    match = re.search(
        r"\+CREG:\s*\d+,\s*(\d+)",
        response
    )

    if not match:

        return "UNKNOWN"


    status = match.group(1)


    if status == "1":

        return "REGISTERED_HOME"


    if status == "5":

        return "REGISTERED_ROAMING"


    if status == "2":

        return "SEARCHING"


    if status == "0":

        return "NOT_REGISTERED"


    return "UNKNOWN"


# ============================================================
# OPERATOR
# ============================================================

def get_operator():

    response = send_at(
        "AT+COPS?",
        5
    )

    match = re.search(
        r'\+COPS:\s*\d+,\s*\d+,\s*"([^"]+)"',
        response
    )

    if match:

        return match.group(1)

    return None


# ============================================================
# LATENCY
# ============================================================

def get_latency():

    response = send_at(
        'AT+QPING=1,"8.8.8.8",5,1',
        8
    )

    match = re.search(
        r"time[=:]\s*(\d+(?:\.\d+)?)",
        response,
        re.IGNORECASE
    )

    if match:

        return float(
            match.group(1)
        )


    return None


# ============================================================
# START GNSS
# ============================================================

def start_gnss():

    response = send_at(
        "AT+QGPS=1",
        5
    )

    if "OK" in response:

        print(
            "🛰️ GNSS enabled",
            flush=True
        )

        return True


    # Some firmware returns an error if it is already enabled.

    if "CME ERROR: 504" in response:

        print(
            "🛰️ GNSS already enabled",
            flush=True
        )

        return True


    print(
        "⚠️ GNSS could not be enabled",
        flush=True
    )

    return False


# ============================================================
# CONVERT GNSS COORDINATE
# ============================================================

def convert_coordinate(value):

    if not value:

        return None


    value = value.strip()


    # --------------------------------------------------------
    # Already decimal format
    # --------------------------------------------------------

    try:

        number = float(value)

        if -180 <= number <= 180:

            return round(
                number,
                7
            )

    except:

        pass


    # --------------------------------------------------------
    # DDMM.MMMM N/S
    # DDDMM.MMMM E/W
    #
    # Example:
    #
    # 1833.4548N
    # 07347.5663E
    # --------------------------------------------------------

    if value[-1] not in [
        "N",
        "S",
        "E",
        "W"
    ]:

        return None


    direction = value[-1]

    number = value[:-1]


    try:

        ddmm = float(number)

    except:

        return None


    degrees = int(
        ddmm / 100
    )

    minutes = (
        ddmm -
        (degrees * 100)
    )


    decimal = (
        degrees +
        (minutes / 60)
    )


    if direction in [
        "S",
        "W"
    ]:

        decimal = -decimal


    return round(
        decimal,
        7
    )


# ============================================================
# GET GNSS LOCATION
# ============================================================

def get_gnss_location():

    response = send_at(
        "AT+QGPSLOC=0",
        GNSS_TIMEOUT
    )


    if not response:

        return None


    # --------------------------------------------------------
    # Exact format from YOUR module:
    #
    # +QGPSLOC:
    # 084025.000,
    # 1833.4548N,
    # 07347.5663E,
    # 1.8,
    # 420.9,
    # 3,
    # 000.00,
    # 0.4,
    # 0.2,
    # 030926,
    # 06
    #
    # fields:
    #
    # 0 = UTC
    # 1 = Latitude
    # 2 = Longitude
    # 3 = HDOP
    # 4 = Altitude
    # 5 = Fix
    # 6 = Course
    # 7 = Speed
    # 8 = ...
    # 9 = Date
    # 10 = Satellites
    # --------------------------------------------------------

    match = re.search(
        r"\+QGPSLOC:\s*([^\r\n]+)",
        response
    )


    if not match:

        return None


    line = match.group(1).strip()


    fields = [
        x.strip()
        for x in line.split(",")
    ]


    if len(fields) < 11:

        print(
            f"⚠️ Unexpected QGPSLOC fields: {fields}",
            flush=True
        )

        return None


    try:

        utc_time = fields[0]

        latitude_raw = fields[1]

        longitude_raw = fields[2]

        hdop_raw = fields[3]

        altitude_raw = fields[4]

        fix_raw = fields[5]

        date_raw = fields[9]

        satellites_raw = fields[10]


        # ----------------------------------------------------
        # CONVERT LATITUDE
        # ----------------------------------------------------

        latitude = convert_coordinate(
            latitude_raw
        )


        # ----------------------------------------------------
        # CONVERT LONGITUDE
        # ----------------------------------------------------

        longitude = convert_coordinate(
            longitude_raw
        )


        if latitude is None:

            return None


        if longitude is None:

            return None


        # ----------------------------------------------------
        # ALTITUDE
        # ----------------------------------------------------

        try:

            altitude = float(
                altitude_raw
            )

        except:

            altitude = None


        # ----------------------------------------------------
        # SATELLITES
        # ----------------------------------------------------

        try:

            satellites = int(
                satellites_raw
            )

        except:

            satellites = None


        # ----------------------------------------------------
        # VALID GNSS FIX
        # ----------------------------------------------------

        # Your response has:
        #
        # fix = 3
        #
        # and valid latitude/longitude.

        return {

            "gnss_status": "FIX",

            "latitude": latitude,

            "longitude": longitude,

            "altitude_m": altitude,

            "satellites": satellites,

            "gps_utc": utc_time

        }


    except Exception as e:

        print(
            f"⚠️ GNSS parsing error: {e}",
            flush=True
        )

        return None


# ============================================================
# UPDATE GSM DATA
# ============================================================

def update_gsm():

    global gsm_data


    if not check_modem():

        gsm_data["gsm_status"] = "Disconnected"

        return


    gsm_data["gsm_status"] = "Connected"


    gsm_data["sim_status"] = (
        get_sim_status()
    )


    gsm_data["sim_iccid"] = (
        get_iccid()
    )


    mobile_number = get_mobile_number()

    if mobile_number:

        gsm_data["mobile_number"] = (
            mobile_number
        )


    signal, dbm = get_signal()


    gsm_data["signal_strength"] = signal

    gsm_data["signal_dbm"] = dbm


    gsm_data["network_status"] = (
        get_network_status()
    )


    operator = get_operator()

    if operator:

        gsm_data["operator"] = operator


    gsm_data["latency_ms"] = (
        get_latency()
    )


# ============================================================
# UPDATE GNSS
# ============================================================

def update_gnss():

    global gnss_data
    global gnss_fix_available
    global gps_fix_record_pending


    location = get_gnss_location()


    # ========================================================
    # VALID GPS FIX RECEIVED
    # ========================================================

    if location:

        # ----------------------------------------------------
        # FIRST VALID FIX
        # ----------------------------------------------------

        if not gnss_fix_available:

            gnss_fix_available = True

            # IMPORTANT:
            #
            # This creates exactly ONE DB record.
            #
            # It does NOT depend on pressure threshold.

            gps_fix_record_pending = True


            print(
                "\n🛰️✅ FIRST GNSS FIX RECEIVED",
                flush=True
            )

            print(
                "📥 One GNSS record will be stored in SQLite",
                flush=True
            )


        # ----------------------------------------------------
        # UPDATE LATEST LOCATION
        # ----------------------------------------------------

        gnss_data.update(
            location
        )


        print(
            f"📍 GNSS FIX | "
            f"LAT={gnss_data['latitude']} | "
            f"LON={gnss_data['longitude']} | "
            f"ALT={gnss_data['altitude_m']} m | "
            f"SAT={gnss_data['satellites']}",
            flush=True
        )


    # ========================================================
    # NO NEW GPS FIX
    # ========================================================

    else:

        if not gnss_fix_available:

            gnss_data["gnss_status"] = "NO_FIX"

            print(
                "🛰️ GNSS → NO_FIX",
                flush=True
            )


        else:

            # Keep previous valid GPS location.

            gnss_data["gnss_status"] = "LAST_FIX"

            print(
                "🛰️ No new GNSS fix → "
                "keeping last valid location",
                flush=True
            )


# ============================================================
# INSERT COMPLETE RECORD
# ============================================================

def insert_record(
    current_raw,
    timestamp
):

    cursor.execute(
        """
        INSERT INTO brake_pressure_log
        (
            device_id,

            BP_raw,
            FP_raw,
            CR_raw,
            BC_raw,

            timestamp,

            uploaded,

            gsm_status,
            sim_status,
            sim_iccid,
            mobile_number,

            signal_strength,
            signal_dbm,

            network_status,
            operator,
            latency_ms,

            gnss_status,
            latitude,
            longitude,
            altitude_m,
            satellites,
            gps_utc
        )

        VALUES
        (
            ?, ?, ?, ?, ?,

            ?,

            0,

            ?, ?, ?, ?,

            ?, ?,

            ?, ?, ?,

            ?, ?, ?, ?, ?, ?
        )
        """,

        (

            DEVICE_ID,

            current_raw[0],
            current_raw[1],
            current_raw[2],
            current_raw[3],

            timestamp,

            # ---------------- GSM ----------------

            gsm_data["gsm_status"],

            gsm_data["sim_status"],

            gsm_data["sim_iccid"],

            gsm_data["mobile_number"],

            gsm_data["signal_strength"],

            gsm_data["signal_dbm"],

            gsm_data["network_status"],

            gsm_data["operator"],

            gsm_data["latency_ms"],

            # ---------------- GNSS ----------------

            gnss_data["gnss_status"],

            gnss_data["latitude"],

            gnss_data["longitude"],

            gnss_data["altitude_m"],

            gnss_data["satellites"],

            gnss_data["gps_utc"]
        )
    )


    conn.commit()


    return cursor.lastrowid


# ============================================================
# INITIALIZE EC200U
# ============================================================

gsm_available = open_gsm()


if gsm_available:

    if check_modem():

        print(
            "✅ EC200U responding",
            flush=True
        )

        start_gnss()

    else:

        print(
            "⚠️ EC200U not responding",
            flush=True
        )


# ============================================================
# TIMERS
# ============================================================

last_gsm_update = 0

last_gnss_update = 0


# ============================================================
# MAIN LOOP
# ============================================================

print(
    "\n🚀 Capture system started",
    flush=True
)

print(
    f"📊 RAW_THRESHOLD = {RAW_THRESHOLD}",
    flush=True
)

print(
    f"⏱ READ_INTERVAL = {READ_INTERVAL} sec",
    flush=True
)

print(
    f"🛰️ GNSS interval = {GNSS_REFRESH_INTERVAL} sec",
    flush=True
)

print(
    "\n📌 DATABASE LOGIC:",
    flush=True
)

print(
    "1. First pressure reading → store",
    flush=True
)

print(
    "2. First GNSS FIX → store ONE additional record",
    flush=True
)

print(
    "3. GPS polling without pressure change → SKIP",
    flush=True
)

print(
    "4. Pressure change >= 326 → store",
    flush=True
)

print(
    "5. Pressure change < 326 → SKIP",
    flush=True
)

print(
    "6. GPS-only record does NOT change last_raw",
    flush=True
)

print(
    "",
    flush=True
)


# ============================================================
# IMPORTANT:
# last_raw is ONLY changed after a PRESSURE-BASED record.
#
# GPS-only records NEVER change last_raw.
# ============================================================

last_raw = None


try:

    while True:

        current_time = time.time()


        # ====================================================
        # GSM REFRESH
        # ====================================================

        if (
            gsm_available
            and
            (
                current_time -
                last_gsm_update
            ) >= GSM_REFRESH_INTERVAL
        ):

            try:

                print(
                    "\n📡 Updating GSM information...",
                    flush=True
                )

                update_gsm()

            except Exception as e:

                print(
                    f"⚠️ GSM update error: {e}",
                    flush=True
                )


            last_gsm_update = current_time


        # ====================================================
        # GNSS REFRESH
        # ====================================================

        if (
            gsm_available
            and
            (
                current_time -
                last_gnss_update
            ) >= GNSS_REFRESH_INTERVAL
        ):

            try:

                print(
                    "\n🛰️ Checking GNSS...",
                    flush=True
                )

                update_gnss()

            except Exception as e:

                print(
                    f"⚠️ GNSS update error: {e}",
                    flush=True
                )


            last_gnss_update = current_time


        # ====================================================
        # READ PRESSURE
        # ====================================================

        current_raw = read_raw_values()


        timestamp = time.strftime(
            "%Y-%m-%d %H:%M:%S"
        )


        # ====================================================
        # YOUR ORIGINAL PRESSURE LOGIC
        # ====================================================

        pressure_record = False


        if last_raw is None:

            # FIRST PRESSURE READING

            pressure_record = True


        else:

            diffs = [

                abs(
                    current_raw[i]
                    -
                    last_raw[i]
                )

                for i in range(4)
            ]


            if any(
                diff >= RAW_THRESHOLD
                for diff in diffs
            ):

                pressure_record = True


        # ====================================================
        # GPS FIRST-FIX RECORD
        # ====================================================

        gps_record = gps_fix_record_pending


        # ====================================================
        # FINAL STORE DECISION
        # ====================================================

        store_record = (
            pressure_record
            or
            gps_record
        )


        # ====================================================
        # DISPLAY
        # ====================================================

        print(
            f"device_id={DEVICE_ID}, "
            f"BP_raw={current_raw[0]}, "
            f"FP_raw={current_raw[1]}, "
            f"CR_raw={current_raw[2]}, "
            f"BC_raw={current_raw[3]}, "
            f"GNSS={gnss_data['gnss_status']}, "
            f"LAT={gnss_data['latitude']}, "
            f"LON={gnss_data['longitude']}, "
            f"SAT={gnss_data['satellites']}",
            flush=True
        )


        # ====================================================
        # STORE
        # ====================================================

        if store_record:

            try:

                record_id = insert_record(
                    current_raw,
                    timestamp
                )


                # --------------------------------------------
                # GPS FIRST FIX RECORD
                # --------------------------------------------

                if gps_record:

                    print(
                        "\n🛰️📥 FIRST GNSS FIX STORED",
                        flush=True
                    )

                    print(
                        f"   DB ID       : {record_id}",
                        flush=True
                    )

                    print(
                        f"   Latitude    : "
                        f"{gnss_data['latitude']}",
                        flush=True
                    )

                    print(
                        f"   Longitude   : "
                        f"{gnss_data['longitude']}",
                        flush=True
                    )

                    print(
                        f"   Altitude    : "
                        f"{gnss_data['altitude_m']} m",
                        flush=True
                    )

                    print(
                        f"   Satellites  : "
                        f"{gnss_data['satellites']}",
                        flush=True
                    )


                    # IMPORTANT:
                    # First-fix event is now consumed.

                    gps_fix_record_pending = False


                # --------------------------------------------
                # PRESSURE RECORD
                # --------------------------------------------

                if pressure_record:

                    # IMPORTANT:
                    #
                    # EXACTLY YOUR EXISTING LOGIC:
                    #
                    # last_raw changes ONLY when a pressure
                    # record is stored.

                    last_raw = current_raw


                    print(
                        "\n📥 PRESSURE RECORD STORED",
                        flush=True
                    )

                    print(
                        f"   DB ID      : {record_id}",
                        flush=True
                    )

                    print(
                        f"   BP/FP/CR/BC: "
                        f"{current_raw[0]} / "
                        f"{current_raw[1]} / "
                        f"{current_raw[2]} / "
                        f"{current_raw[3]}",
                        flush=True
                    )

                    print(
                        f"   GNSS       : "
                        f"{gnss_data['gnss_status']}",
                        flush=True
                    )

                    print(
                        f"   Latitude   : "
                        f"{gnss_data['latitude']}",
                        flush=True
                    )

                    print(
                        f"   Longitude  : "
                        f"{gnss_data['longitude']}",
                        flush=True
                    )

                    print(
                        f"   Satellites : "
                        f"{gnss_data['satellites']}",
                        flush=True
                    )

                    print(
                        "   Uploaded   : 0",
                        flush=True
                    )


                print(
                    "",
                    flush=True
                )


            except Exception as e:

                print(
                    f"❌ DB insert failed: {e}",
                    flush=True
                )

                # GPS pending remains TRUE if insert failed.
                # Therefore it will be retried.


        # ====================================================
        # SKIP
        # ====================================================

        else:

            print(
                "⏭ No significant pressure change "
                "→ Skipped DB insert",
                flush=True
            )


        # ====================================================
        # PRESSURE SAMPLING INTERVAL
        # ====================================================

        time.sleep(
            READ_INTERVAL
        )


# ============================================================
# STOP
# ============================================================

except KeyboardInterrupt:

    print(
        "\n🛑 Capture stopped by user",
        flush=True
    )


finally:

    try:

        if gsm_serial:

            gsm_serial.close()

    except:

        pass


    try:

        conn.close()

    except:

        pass


    print(
        "✅ Capture system closed",
        flush=True
    )