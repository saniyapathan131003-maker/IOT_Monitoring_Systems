#!/usr/bin/env python3

import os
import time
import sqlite3
import serial
import re

import board
import busio
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn


# ============================================================
# CONFIGURATION
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DB_PATH = os.path.join(
    BASE_DIR,
    "db",
    "new_db.db"
)

# ---------------- GSM / EC200U ----------------

GSM_PORT = "/dev/ttyAMA3"
GSM_BAUDRATE = 115200

# Retry serial connection
GSM_RECONNECT_INTERVAL = 5

# GSM information refresh
GSM_INTERVAL = 30

# GNSS polling
GNSS_INTERVAL = 5
GNSS_TIMEOUT = 10

# ---------------- PRESSURE ----------------

RAW_THRESHOLD = 326

READ_INTERVAL = 0.1


# ============================================================
# DATABASE
# ============================================================

os.makedirs(
    os.path.dirname(DB_PATH),
    exist_ok=True
)

conn = sqlite3.connect(
    DB_PATH,
    timeout=30
)

cursor = conn.cursor()

cursor.execute(
    "PRAGMA journal_mode=WAL"
)

cursor.execute(
    "PRAGMA busy_timeout=30000"
)


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

    timestamp TEXT,

    uploaded INTEGER DEFAULT 0,

    gsm_status TEXT,
    sim_status TEXT,
    sim_iccid TEXT,
    mobile_number TEXT,
    signal_strength INTEGER,
    signal_dbm INTEGER,
    network_status TEXT,
    operator TEXT,
    latency_ms REAL,

    gnss_status TEXT,
    latitude REAL,
    longitude REAL,
    altitude_m REAL,
    satellites INTEGER,
    gps_utc TEXT
)
""")

conn.commit()


# ============================================================
# ADD MISSING COLUMNS
# ============================================================

def add_column_if_missing(
    column_name,
    column_type
):

    cursor.execute(
        "PRAGMA table_info(brake_pressure_log)"
    )

    columns = [
        row[1]
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


add_column_if_missing(
    "gsm_status",
    "TEXT"
)

add_column_if_missing(
    "sim_status",
    "TEXT"
)

add_column_if_missing(
    "sim_iccid",
    "TEXT"
)

add_column_if_missing(
    "mobile_number",
    "TEXT"
)

add_column_if_missing(
    "signal_strength",
    "INTEGER"
)

add_column_if_missing(
    "signal_dbm",
    "INTEGER"
)

add_column_if_missing(
    "network_status",
    "TEXT"
)

add_column_if_missing(
    "operator",
    "TEXT"
)

add_column_if_missing(
    "latency_ms",
    "REAL"
)

add_column_if_missing(
    "gnss_status",
    "TEXT"
)

add_column_if_missing(
    "latitude",
    "REAL"
)

add_column_if_missing(
    "longitude",
    "REAL"
)

add_column_if_missing(
    "altitude_m",
    "REAL"
)

add_column_if_missing(
    "satellites",
    "INTEGER"
)

add_column_if_missing(
    "gps_utc",
    "TEXT"
)


# ============================================================
# DEVICE ID
# ============================================================

DEVICE_ID = "UNKNOWN"

try:

    cursor.execute("""
        SELECT device_id
        FROM device_config
        LIMIT 1
    """)

    result = cursor.fetchone()

    if result and result[0]:

        DEVICE_ID = str(
            result[0]
        )

except Exception:

    pass


print()
print("=" * 75)
print(f"✅ Device ID = {DEVICE_ID}")
print("=" * 75)


# ============================================================
# ADS1115
# ============================================================

try:

    i2c = busio.I2C(
        board.SCL,
        board.SDA
    )

    ads = ADS.ADS1115(i2c)

    ads.gain = 1

    BP_channel = AnalogIn(
        ads,
        0
    )

    FP_channel = AnalogIn(
        ads,
        1
    )

    CR_channel = AnalogIn(
        ads,
        2
    )

    BC_channel = AnalogIn(
        ads,
        3
    )

    print(
        "✅ ADS1115 initialized"
    )

except Exception as e:

    print(
        "❌ ADS1115 initialization failed"
    )

    print(
        "Error:",
        e
    )

    conn.close()

    raise


# ============================================================
# EC200U SERIAL OBJECT
# ============================================================

gsm_serial = None

last_gsm_reconnect_attempt = 0


# ============================================================
# GSM CACHE
# ============================================================

gsm_data = {

    "gsm_status": "Disconnected",

    "sim_status": None,

    "sim_iccid": None,

    "mobile_number": None,

    "signal_strength": None,

    "signal_dbm": None,

    "network_status": "UNKNOWN",

    "operator": None,

    "latency_ms": None
}


# ============================================================
# GNSS CACHE
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
# GPS FIRST-FIX FLAGS
# ============================================================

gnss_fix_available = False

gps_fix_record_pending = False


# ============================================================
# CLOSE GSM
# ============================================================

def close_gsm():

    global gsm_serial

    if gsm_serial is not None:

        try:

            gsm_serial.close()

        except Exception:

            pass

    gsm_serial = None

    gsm_data["gsm_status"] = "Disconnected"

    gsm_data["network_status"] = "UNKNOWN"


# ============================================================
# OPEN GSM
# ============================================================

def open_gsm():

    global gsm_serial

    try:

        # Close previous connection first
        close_gsm()

        gsm_serial = serial.Serial(
            GSM_PORT,
            GSM_BAUDRATE,
            timeout=1,
            write_timeout=2
        )

        time.sleep(0.5)

        print()
        print(
            f"🔌 EC200U UART opened: "
            f"{GSM_PORT}"
        )

        return True

    except Exception as e:

        gsm_serial = None

        print(
            f"❌ EC200U UART open failed: "
            f"{e}"
        )

        return False


# ============================================================
# SEND AT COMMAND
# ============================================================

def send_at(
    command,
    timeout=3
):

    global gsm_serial

    if gsm_serial is None:

        return ""

    try:

        gsm_serial.reset_input_buffer()

        gsm_serial.write(
            (
                command + "\r"
            ).encode()
        )

        gsm_serial.flush()

        start_time = time.time()

        response = ""

        while (
            time.time() - start_time
            < timeout
        ):

            if gsm_serial.in_waiting:

                data = gsm_serial.read(
                    gsm_serial.in_waiting
                ).decode(
                    errors="ignore"
                )

                response += data

                if (
                    "\r\nOK\r\n"
                    in response
                ):

                    break

                if (
                    "\r\nERROR\r\n"
                    in response
                ):

                    break

            time.sleep(0.05)

        return response.strip()

    except (
        serial.SerialException,
        OSError,
        Exception
    ) as e:

        print(
            f"⚠️ EC200U communication error: "
            f"{e}"
        )

        close_gsm()

        return ""


# ============================================================
# CHECK MODEM
# ============================================================

def check_modem():

    if gsm_serial is None:

        return False

    response = send_at(
        "AT",
        timeout=2
    )

    if "OK" in response:

        return True

    return False


# ============================================================
# INITIALIZE / RECOVER EC200U
# ============================================================

def recover_ec200u():

    global last_gsm_reconnect_attempt

    current_time = time.time()

    if (
        current_time
        - last_gsm_reconnect_attempt
        < GSM_RECONNECT_INTERVAL
    ):

        return False

    last_gsm_reconnect_attempt = (
        current_time
    )

    print()
    print(
        "🔄 Attempting EC200U reconnect..."
    )

    close_gsm()

    if not open_gsm():

        print(
            "❌ EC200U reconnect failed"
        )

        return False

    if not check_modem():

        print(
            "❌ EC200U opened but "
            "not responding to AT"
        )

        close_gsm()

        return False

    print(
        "✅ EC200U reconnected successfully"
    )

    # Restart GNSS after modem recovery
    start_gnss()

    return True


# ============================================================
# ENSURE MODEM CONNECTION
# ============================================================

def ensure_modem():

    global gsm_serial

    if gsm_serial is None:

        return recover_ec200u()

    # Check modem
    if check_modem():

        return True

    print()
    print(
        "⚠️ EC200U is not responding"
    )

    return recover_ec200u()


# ============================================================
# SIM STATUS
# ============================================================

def get_sim_status():

    response = send_at(
        "AT+CPIN?",
        timeout=3
    )

    if "READY" in response:

        return "READY"

    if "SIM PIN" in response:

        return "SIM_PIN"

    return "UNKNOWN"


# ============================================================
# ICCID
# ============================================================

def get_iccid():

    response = send_at(
        "AT+QCCID",
        timeout=3
    )

    match = re.search(
        r'\+QCCID:\s*"?([0-9]+)"?',
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
        timeout=5
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
        timeout=3
    )

    match = re.search(
        r'\+CSQ:\s*(\d+),(\d+)',
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
# NETWORK REGISTRATION
# ============================================================

def get_network_status():

    response = send_at(
        "AT+CREG?",
        timeout=3
    )

    match = re.search(
        r'\+CREG:\s*\d+,\s*(\d+)',
        response
    )

    if not match:

        return "UNKNOWN"

    status = match.group(1)

    if status in ("1", "5"):

        return "REGISTERED"

    if status == "2":

        return "SEARCHING"

    if status == "3":

        return "REGISTRATION_DENIED"

    if status == "0":

        return "NOT_REGISTERED"

    return "UNKNOWN"


# ============================================================
# OPERATOR
# ============================================================

def get_operator():

    response = send_at(
        "AT+COPS?",
        timeout=8
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
        timeout=10
    )

    match = re.search(
        r'time[=:]\s*(\d+(?:\.\d+)?)',
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

    if gsm_serial is None:

        return False

    print(
        "🛰️ Starting / checking GNSS..."
    )

    response = send_at(
        "AT+QGPS=1",
        timeout=5
    )

    if "OK" in response:

        print(
            "🛰️✅ GNSS enabled"
        )

        return True

    if "ERROR" in response:

        # Verify whether GNSS is already running
        check = send_at(
            "AT+QGPS?",
            timeout=3
        )

        if "+QGPS: 1" in check:

            print(
                "🛰️✅ GNSS already enabled"
            )

            return True

        print(
            "⚠️ GNSS start failed"
        )

        return False

    return False


# ============================================================
# COORDINATE CONVERSION
# ============================================================

def convert_coordinate(value):

    if value is None:

        return None

    value = str(
        value
    ).strip()

    if not value:

        return None

    # Decimal coordinate
    try:

        decimal_value = float(
            value
        )

        if -180 <= decimal_value <= 180:

            return decimal_value

    except ValueError:

        pass

    # DDMM.MMMM + direction
    match = re.match(
        r'^(\d+)(\d{2}\.\d+)([NSEW])$',
        value.upper()
    )

    if not match:

        return None

    degrees = float(
        match.group(1)
    )

    minutes = float(
        match.group(2)
    )

    direction = match.group(3)

    decimal_value = (
        degrees
        + minutes / 60.0
    )

    if direction in (
        "S",
        "W"
    ):

        decimal_value = -decimal_value

    return decimal_value


# ============================================================
# GET GNSS LOCATION
# ============================================================

def get_gnss_location():

    response = send_at(
        "AT+QGPSLOC=0",
        timeout=GNSS_TIMEOUT
    )

    if "+QGPSLOC:" not in response:

        return None

    match = re.search(
        r'\+QGPSLOC:\s*([^\r\n]+)',
        response
    )

    if not match:

        return None

    fields = [
        x.strip()
        for x in
        match.group(1).split(",")
    ]

    if len(fields) < 8:

        return None

    latitude = convert_coordinate(
        fields[0]
    )

    longitude = convert_coordinate(
        fields[1]
    )

    if (
        latitude is None
        or longitude is None
    ):

        return None

    try:

        altitude = float(
            fields[3]
        )

    except Exception:

        altitude = None

    try:

        fix_value = fields[4]

    except Exception:

        fix_value = None

    # No fix
    if fix_value == "0":

        return None

    gps_utc = None

    if len(fields) >= 8:

        gps_utc = fields[7]

    return {

        "status": "FIX",

        "latitude": latitude,

        "longitude": longitude,

        "altitude_m": altitude,

        "satellites": None,

        "gps_utc": gps_utc
    }


# ============================================================
# UPDATE GSM
# ============================================================

def update_gsm():

    global gsm_data

    print()
    print(
        "📡 Updating GSM information..."
    )

    if not ensure_modem():

        gsm_data["gsm_status"] = (
            "Disconnected"
        )

        print(
            "❌ GSM disconnected"
        )

        return False

    gsm_data["gsm_status"] = (
        "Connected"
    )

    gsm_data["sim_status"] = (
        get_sim_status()
    )

    gsm_data["sim_iccid"] = (
        get_iccid()
    )

    gsm_data["mobile_number"] = (
        get_mobile_number()
    )

    rssi, dbm = get_signal()

    gsm_data["signal_strength"] = (
        rssi
    )

    gsm_data["signal_dbm"] = (
        dbm
    )

    gsm_data["network_status"] = (
        get_network_status()
    )

    gsm_data["operator"] = (
        get_operator()
    )

    # Only ping if network is registered
    if gsm_data["network_status"] in (
        "REGISTERED",
    ):

        gsm_data["latency_ms"] = (
            get_latency()
        )

    else:

        gsm_data["latency_ms"] = None

    print()
    print("📡 GSM INFORMATION")

    print(
        f"   GSM Status    : "
        f"{gsm_data['gsm_status']}"
    )

    print(
        f"   SIM Status    : "
        f"{gsm_data['sim_status']}"
    )

    print(
        f"   ICCID         : "
        f"{gsm_data['sim_iccid']}"
    )

    print(
        f"   Mobile Number : "
        f"{gsm_data['mobile_number']}"
    )

    print(
        f"   Signal RSSI   : "
        f"{gsm_data['signal_strength']}"
    )

    print(
        f"   Signal dBm    : "
        f"{gsm_data['signal_dbm']}"
    )

    print(
        f"   Network       : "
        f"{gsm_data['network_status']}"
    )

    print(
        f"   Operator      : "
        f"{gsm_data['operator']}"
    )

    print(
        f"   Latency       : "
        f"{gsm_data['latency_ms']} ms"
    )

    return True


# ============================================================
# UPDATE GNSS
# ============================================================

def update_gnss():

    global gnss_data
    global gnss_fix_available
    global gps_fix_record_pending

    print()
    print(
        "🛰️ Checking GNSS..."
    )

    # If modem is disconnected,
    # do not try GNSS.
    if gsm_serial is None:

        print(
            "⚠️ GNSS unavailable - "
            "EC200U disconnected"
        )

        return False

    location = get_gnss_location()

    if location is None:

        if not gnss_fix_available:

            gnss_data["gnss_status"] = (
                "NO_FIX"
            )

            print(
                "🛰️ GNSS: NO FIX"
            )

        else:

            gnss_data["gnss_status"] = (
                "LAST_FIX"
            )

            print(
                "🛰️ GNSS: LAST FIX"
            )

        return False

    # ========================================================
    # VALID FIX
    # ========================================================

    gnss_data["gnss_status"] = "FIX"

    gnss_data["latitude"] = (
        location["latitude"]
    )

    gnss_data["longitude"] = (
        location["longitude"]
    )

    gnss_data["altitude_m"] = (
        location["altitude_m"]
    )

    gnss_data["satellites"] = (
        location["satellites"]
    )

    gnss_data["gps_utc"] = (
        location["gps_utc"]
    )

    # ========================================================
    # FIRST FIX
    # ========================================================

    if not gnss_fix_available:

        gnss_fix_available = True

        gps_fix_record_pending = True

        print()
        print(
            "🛰️✅ FIRST GNSS FIX RECEIVED"
        )

        print(
            "📥 One GNSS record will be "
            "stored in SQLite"
        )

    else:

        print(
            "🛰️ GNSS FIX UPDATED"
        )

    print(
        f"📍 GNSS FIX | "
        f"LAT={gnss_data['latitude']} | "
        f"LON={gnss_data['longitude']} | "
        f"ALT={gnss_data['altitude_m']} m | "
        f"SAT={gnss_data['satellites']}"
    )

    return True


# ============================================================
# READ PRESSURE
# ============================================================

def read_pressure():

    BP_raw = BP_channel.value

    FP_raw = FP_channel.value

    CR_raw = CR_channel.value

    BC_raw = BC_channel.value

    return (
        BP_raw,
        FP_raw,
        CR_raw,
        BC_raw
    )


# ============================================================
# INSERT DATABASE
# ============================================================

def insert_record(
    raw_values
):

    BP_raw, FP_raw, CR_raw, BC_raw = (
        raw_values
    )

    timestamp = time.strftime(
        "%Y-%m-%d %H:%M:%S"
    )

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
            ?,
            ?,
            ?,
            ?,
            ?,
            ?,
            0,
            ?,
            ?,
            ?,
            ?,
            ?,
            ?,
            ?,
            ?,
            ?,
            ?,
            ?,
            ?,
            ?,
            ?,
            ?,
            ?
        )
        """,

        (

            DEVICE_ID,

            BP_raw,
            FP_raw,
            CR_raw,
            BC_raw,

            timestamp,

            gsm_data["gsm_status"],
            gsm_data["sim_status"],
            gsm_data["sim_iccid"],
            gsm_data["mobile_number"],
            gsm_data["signal_strength"],
            gsm_data["signal_dbm"],
            gsm_data["network_status"],
            gsm_data["operator"],
            gsm_data["latency_ms"],

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
# PRINT DATABASE RECORD
# ============================================================

def print_record(
    row_id,
    raw_values,
    reason
):

    BP_raw, FP_raw, CR_raw, BC_raw = (
        raw_values
    )

    print()
    print("=" * 75)

    print(
        f"💾 DATABASE INSERT | "
        f"REASON = {reason}"
    )

    print(
        f"   DB ID       : {row_id}"
    )

    print(
        f"   Device ID   : {DEVICE_ID}"
    )

    print()

    print("📊 PRESSURE")

    print(
        f"   BP_raw      : {BP_raw}"
    )

    print(
        f"   FP_raw      : {FP_raw}"
    )

    print(
        f"   CR_raw      : {CR_raw}"
    )

    print(
        f"   BC_raw      : {BC_raw}"
    )

    print()

    print("📡 GSM")

    print(
        f"   Status      : "
        f"{gsm_data['gsm_status']}"
    )

    print(
        f"   SIM         : "
        f"{gsm_data['sim_status']}"
    )

    print(
        f"   RSSI        : "
        f"{gsm_data['signal_strength']}"
    )

    print(
        f"   dBm         : "
        f"{gsm_data['signal_dbm']}"
    )

    print(
        f"   Network     : "
        f"{gsm_data['network_status']}"
    )

    print(
        f"   Operator    : "
        f"{gsm_data['operator']}"
    )

    print(
        f"   Latency     : "
        f"{gsm_data['latency_ms']} ms"
    )

    print()

    print("🛰️ GNSS")

    print(
        f"   Status      : "
        f"{gnss_data['gnss_status']}"
    )

    print(
        f"   Latitude    : "
        f"{gnss_data['latitude']}"
    )

    print(
        f"   Longitude   : "
        f"{gnss_data['longitude']}"
    )

    print(
        f"   Altitude    : "
        f"{gnss_data['altitude_m']} m"
    )

    print(
        f"   Satellites  : "
        f"{gnss_data['satellites']}"
    )

    print(
        f"   GPS UTC     : "
        f"{gnss_data['gps_utc']}"
    )

    print("=" * 75)


# ============================================================
# INITIAL EC200U CONNECTION
# ============================================================

print()
print(
    "🔌 Initializing EC200U..."
)

if open_gsm():

    if check_modem():

        print(
            "✅ EC200U responding"
        )

        start_gnss()

    else:

        print(
            "⚠️ EC200U opened but "
            "not responding"
        )

        close_gsm()

else:

    print(
        "⚠️ EC200U not available"
    )

    print(
        "🔄 Automatic reconnect will continue"
    )


# ============================================================
# STARTUP INFORMATION
# ============================================================

print()
print("=" * 75)
print("🚀 Capture system started")
print("=" * 75)

print(
    f"📊 RAW_THRESHOLD = "
    f"{RAW_THRESHOLD}"
)

print(
    f"⏱ READ_INTERVAL = "
    f"{READ_INTERVAL} sec"
)

print(
    f"📡 GSM interval = "
    f"{GSM_INTERVAL} sec"
)

print(
    f"🛰️ GNSS interval = "
    f"{GNSS_INTERVAL} sec"
)

print()
print("📌 DATABASE LOGIC")

print(
    "1. First pressure reading → STORE"
)

print(
    "2. First GNSS FIX → STORE ONE additional record"
)

print(
    "3. GPS polling without pressure change → SKIP"
)

print(
    f"4. Any pressure difference >= "
    f"{RAW_THRESHOLD} → STORE ALL 4 readings"
)

print(
    f"5. Pressure difference < "
    f"{RAW_THRESHOLD} → SKIP"
)

print(
    "6. GPS-only record does NOT change last_raw"
)

print(
    "7. GSM disconnect → automatic reconnect"
)

print(
    "8. EC200U recovery → automatic GNSS restart"
)

print(
    "9. Pressure logging continues even if GSM is offline"
)

print("=" * 75)


# ============================================================
# TIMERS
# ============================================================

last_gsm_update = 0

last_gnss_update = 0

last_raw = None


# ============================================================
# MAIN LOOP
# ============================================================

try:

    while True:

        current_time = time.time()

        # ====================================================
        # GSM / EC200U
        # ====================================================

        if (
            current_time
            - last_gsm_update
            >= GSM_INTERVAL
        ):

            update_gsm()

            last_gsm_update = (
                current_time
            )

        # ====================================================
        # GNSS
        # ====================================================

        if (
            current_time
            - last_gnss_update
            >= GNSS_INTERVAL
        ):

            # If modem is disconnected,
            # try reconnect.
            if gsm_serial is None:

                recovered = (
                    recover_ec200u()
                )

                if not recovered:

                    print(
                        "🛰️ GNSS skipped - "
                        "EC200U unavailable"
                    )

            else:

                # Check modem before GNSS
                if check_modem():

                    update_gnss()

                else:

                    print()
                    print(
                        "⚠️ EC200U lost during "
                        "GNSS polling"
                    )

                    close_gsm()

                    recover_ec200u()

            last_gnss_update = (
                current_time
            )

        # ====================================================
        # PRESSURE READ
        # ====================================================

        current_raw = read_pressure()

        # ====================================================
        # PRESSURE DECISION
        # ====================================================

        pressure_record = False

        pressure_reason = ""

        if last_raw is None:

            # ------------------------------------------------
            # FIRST PRESSURE READING
            # ------------------------------------------------

            pressure_record = True

            pressure_reason = (
                "FIRST PRESSURE READING"
            )

        else:

            differences = [

                abs(
                    current_raw[i]
                    - last_raw[i]
                )

                for i in range(4)
            ]

            # ------------------------------------------------
            # ANY CHANNEL >= 326
            # ------------------------------------------------

            if any(
                difference
                >= RAW_THRESHOLD

                for difference
                in differences
            ):

                pressure_record = True

                pressure_reason = (
                    "PRESSURE CHANGE >= "
                    f"{RAW_THRESHOLD}"
                )

                print()
                print(
                    "🚨 PRESSURE CHANGE DETECTED"
                )

                print(
                    f"   BP difference = "
                    f"{differences[0]}"
                )

                print(
                    f"   FP difference = "
                    f"{differences[1]}"
                )

                print(
                    f"   CR difference = "
                    f"{differences[2]}"
                )

                print(
                    f"   BC difference = "
                    f"{differences[3]}"
                )

        # ====================================================
        # FIRST GPS RECORD
        # ====================================================

        gps_record = (
            gps_fix_record_pending
        )

        # ====================================================
        # STORE DECISION
        # ====================================================

        store_record = (
            pressure_record
            or gps_record
        )

        if store_record:

            try:

                # ------------------------------------------------
                # Determine reason
                # ------------------------------------------------

                if pressure_record:

                    reason = pressure_reason

                else:

                    reason = "FIRST GNSS FIX"

                # ------------------------------------------------
                # INSERT
                # ------------------------------------------------

                row_id = insert_record(
                    current_raw
                )

                # ------------------------------------------------
                # PRINT
                # ------------------------------------------------

                print_record(
                    row_id,
                    current_raw,
                    reason
                )

                # ------------------------------------------------
                # IMPORTANT:
                #
                # Update last_raw ONLY because
                # pressure caused the insert.
                # ------------------------------------------------

                if pressure_record:

                    last_raw = current_raw

                    print()
                    print(
                        "✅ last_raw updated "
                        "after pressure record"
                    )

                # ------------------------------------------------
                # FIRST GPS RECORD CONSUMED
                # ------------------------------------------------

                if gps_record:

                    gps_fix_record_pending = (
                        False
                    )

                    print()
                    print(
                        "🛰️📥 FIRST GNSS FIX STORED"
                    )

                    print(
                        f"   DB ID       : "
                        f"{row_id}"
                    )

                    print(
                        f"   Latitude    : "
                        f"{gnss_data['latitude']}"
                    )

                    print(
                        f"   Longitude   : "
                        f"{gnss_data['longitude']}"
                    )

                    print(
                        f"   Altitude    : "
                        f"{gnss_data['altitude_m']} m"
                    )

                    print()
                    print(
                        "✅ Further GPS-only "
                        "records will be ignored"
                    )

            except sqlite3.Error as e:

                print()
                print(
                    "❌ DATABASE INSERT FAILED"
                )

                print(
                    "Error:",
                    e
                )

        # ====================================================
        # NO INSERT
        # ====================================================

        else:

            # No database insertion.
            # Pressure remains available for
            # next comparison.
            pass

        # ====================================================
        # SMALL DELAY
        # ====================================================

        time.sleep(
            READ_INTERVAL
        )


# ============================================================
# STOP
# ============================================================

except KeyboardInterrupt:

    print()
    print(
        "🛑 Capture stopped by user"
    )


except Exception as e:

    print()
    print(
        "❌ Capture system error:"
    )

    print(
        "Error:",
        e
    )


finally:

    close_gsm()

    try:

        conn.close()

    except Exception:

        pass

    print()
    print(
        "🔒 Database connection closed"
    )

    print(
        "🔌 EC200U connection closed"
    )