#!/usr/bin/env python3

import os
import sys
import time
import sqlite3
import serial
import re
import threading


# ============================================================
# CONFIGURATION
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DB_PATH = os.path.join(
    BASE_DIR,
    "db",
    "new_db.db"
)

# EC200U UART
GSM_PORT = "/dev/ttyAMA3"
GSM_BAUDRATE = 115200

# Pressure capture
RAW_THRESHOLD = 326
READ_INTERVAL = 0.1

# GSM/GNSS refresh intervals
GSM_REFRESH_INTERVAL = 30
GNSS_REFRESH_INTERVAL = 5

# GNSS command timeout
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
# ADD NEW COLUMNS SAFELY
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
            f"✅ Added database column: {column_name}",
            flush=True
        )


# GSM fields
add_column_if_missing("gsm_status", "TEXT")
add_column_if_missing("sim_status", "TEXT")
add_column_if_missing("sim_iccid", "TEXT")
add_column_if_missing("mobile_number", "TEXT")
add_column_if_missing("signal_strength", "INTEGER")
add_column_if_missing("signal_dbm", "INTEGER")
add_column_if_missing("network_status", "TEXT")
add_column_if_missing("operator", "TEXT")
add_column_if_missing("latency_ms", "REAL")

# GNSS fields
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
# READ PRESSURE RAW VALUES
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
# GSM VARIABLES
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
# GNSS VARIABLES
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
# GSM SERIAL
# ============================================================

gsm_serial = None

gsm_lock = threading.Lock()


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
            f"✅ EC200U opened on {GSM_PORT}",
            flush=True
        )

        return True


    except Exception as e:

        gsm_serial = None

        print(
            f"❌ EC200U open failed: {e}",
            flush=True
        )

        return False


# ============================================================
# SEND AT COMMAND
# ============================================================

def send_at(command, timeout=2):

    global gsm_serial

    if gsm_serial is None:

        return ""


    with gsm_lock:

        try:

            gsm_serial.reset_input_buffer()

            gsm_serial.write(
                (command + "\r\n").encode()
            )

            gsm_serial.flush()

            start = time.time()

            response = ""


            while time.time() - start < timeout:

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


            print(
                f"\n>>> {command}",
                flush=True
            )

            print(
                response.strip(),
                flush=True
            )


            return response


        except Exception as e:

            print(
                f"❌ AT command error: {e}",
                flush=True
            )

            return ""


# ============================================================
# CHECK MODEM
# ============================================================

def check_modem():

    response = send_at(
        "AT",
        2
    )

    return "OK" in response


# ============================================================
# SIM STATUS
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

    # Example:
    # +CNUM: "","+919XXXXXXXXX",145

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


    # 3GPP approximation
    dbm = (
        -113 + (2 * rssi)
    )


    return rssi, dbm


# ============================================================
# NETWORK REGISTRATION
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

    start = time.time()

    response = send_at(
        'AT+QPING=1,"8.8.8.8",5,1',
        8
    )

    elapsed = (
        time.time() - start
    ) * 1000


    match = re.search(
        r"time[=:]\s*(\d+(?:\.\d+)?)",
        response,
        re.IGNORECASE
    )

    if match:

        return float(
            match.group(1)
        )


    if "OK" in response:

        return round(
            elapsed,
            2
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
            "🛰️ GNSS started",
            flush=True
        )

        return True


    # Already running can also be acceptable
    if "CME ERROR: 504" in response:

        return True


    return False


# ============================================================
# GNSS LOCATION
# ============================================================

def get_gnss_location():

    response = send_at(
        "AT+QGPSLOC=0",
        GNSS_TIMEOUT
    )


    match = re.search(
        r"\+QGPSLOC:\s*"
        r"([^,\r\n]+),"
        r"([^,\r\n]+),"
        r"([^,\r\n]+),"
        r"([^,\r\n]+),"
        r"([^,\r\n]+),"
        r"([^,\r\n]+),"
        r"([^,\r\n]+),"
        r"([^,\r\n]+),"
        r"([^,\r\n]+),"
        r"([^,\r\n]+),"
        r"([^,\r\n]+)",
        response
    )


    if not match:

        return None


    fields = match.groups()


    try:

        utc_time = fields[0]

        latitude_raw = fields[1]

        longitude_raw = fields[2]

        hdop = fields[3]

        altitude = fields[4]

        fix = fields[5]

        satellites = fields[6]

        # Some EC200U firmware versions may return
        # fields differently. Keep the raw values safe.

        latitude = convert_coordinate(
            latitude_raw,
            "lat"
        )

        longitude = convert_coordinate(
            longitude_raw,
            "lon"
        )


        if latitude is None or longitude is None:

            return None


        try:

            altitude_value = float(
                altitude
            )

        except:

            altitude_value = None


        try:

            satellite_value = int(
                satellites
            )

        except:

            satellite_value = None


        return {

            "gnss_status": "FIX",

            "latitude": latitude,

            "longitude": longitude,

            "altitude_m": altitude_value,

            "satellites": satellite_value,

            "gps_utc": utc_time
        }


    except Exception as e:

        print(
            f"⚠️ GNSS parsing error: {e}",
            flush=True
        )

        return None


# ============================================================
# COORDINATE CONVERSION
# ============================================================

def convert_coordinate(value, coordinate_type):

    if not value:

        return None


    value = value.strip()


    # Example:
    # 3150.7223N
    # 11711.9293E

    direction = value[-1]

    number = value[:-1]


    try:

        decimal_minutes = float(
            number
        )

    except:

        return None


    degrees_digits = 2

    if coordinate_type == "lon":

        degrees_digits = 3


    degrees = int(
        decimal_minutes /
        100
    )


    minutes = (
        decimal_minutes -
        (degrees * 100)
    )


    decimal = (
        degrees +
        minutes / 60
    )


    if direction in ["S", "W"]:

        decimal = -decimal


    return round(
        decimal,
        7
    )


# ============================================================
# GSM UPDATE
# ============================================================

def update_gsm_data():

    global gsm_data


    if not check_modem():

        gsm_data["gsm_status"] = "Disconnected"

        return


    gsm_data["gsm_status"] = "Connected"


    gsm_data["sim_status"] = get_sim_status()

    gsm_data["sim_iccid"] = get_iccid()

    gsm_data["mobile_number"] = get_mobile_number()

    signal, dbm = get_signal()

    gsm_data["signal_strength"] = signal

    gsm_data["signal_dbm"] = dbm

    gsm_data["network_status"] = get_network_status()

    gsm_data["operator"] = get_operator()

    gsm_data["latency_ms"] = get_latency()


# ============================================================
# GNSS UPDATE
# ============================================================

def update_gnss_data():

    global gnss_data


    location = get_gnss_location()


    if location:

        gnss_data.update(
            location
        )

        print(
            f"📍 GNSS: "
            f"Lat={location['latitude']}, "
            f"Lon={location['longitude']}, "
            f"Alt={location['altitude_m']} m, "
            f"Sat={location['satellites']}",
            flush=True
        )

    else:

        gnss_data["gnss_status"] = "NO_FIX"

        print(
            "🛰️ GNSS: No position fix",
            flush=True
        )


# ============================================================
# INITIALIZE EC200U
# ============================================================

gsm_available = open_gsm()


if gsm_available:

    # Check modem
    if check_modem():

        print(
            "✅ EC200U responding",
            flush=True
        )

        # Start GNSS
        start_gnss()

    else:

        print(
            "⚠️ EC200U not responding",
            flush=True
        )


# ============================================================
# GSM/GNSS TIMERS
# ============================================================

last_gsm_update = 0

last_gnss_update = 0


# ============================================================
# MAIN LOOP
# ============================================================

print(
    "\n🚀 Capture system started...\n",
    flush=True
)


last_raw = None


try:

    while True:

        current_time = time.time()


        # ====================================================
        # GSM UPDATE
        # ====================================================

        if (
            gsm_available
            and
            current_time - last_gsm_update
            >= GSM_REFRESH_INTERVAL
        ):

            try:

                print(
                    "\n📡 Updating GSM information...",
                    flush=True
                )

                update_gsm_data()

            except Exception as e:

                print(
                    f"⚠️ GSM update error: {e}",
                    flush=True
                )

            last_gsm_update = current_time


        # ====================================================
        # GNSS UPDATE
        # ====================================================

        if (
            gsm_available
            and
            current_time - last_gnss_update
            >= GNSS_REFRESH_INTERVAL
        ):

            try:

                print(
                    "\n🛰️ Updating GNSS location...",
                    flush=True
                )

                update_gnss_data()

            except Exception as e:

                print(
                    f"⚠️ GNSS update error: {e}",
                    flush=True
                )

            last_gnss_update = current_time


        # ====================================================
        # PRESSURE READ
        # ====================================================

        current_raw = read_raw_values()


        timestamp = time.strftime(
            "%Y-%m-%d %H:%M:%S"
        )


        print(
            f"device_id={DEVICE_ID}, "
            f"BP_raw={current_raw[0]}, "
            f"FP_raw={current_raw[1]}, "
            f"CR_raw={current_raw[2]}, "
            f"BC_raw={current_raw[3]}, "
            f"GSM={gsm_data['gsm_status']}, "
            f"NET={gsm_data['network_status']}, "
            f"GNSS={gnss_data['gnss_status']}, "
            f"LAT={gnss_data['latitude']}, "
            f"LON={gnss_data['longitude']}",
            flush=True
        )


        # ====================================================
        # UPLOAD DECISION
        # ====================================================

        upload = False


        if last_raw is None:

            upload = True


        else:

            diffs = [

                abs(
                    current_raw[i] -
                    last_raw[i]
                )

                for i in range(4)
            ]


            if any(
                diff >= RAW_THRESHOLD
                for diff in diffs
            ):

                upload = True


        # ====================================================
        # INSERT DATABASE
        # ====================================================

        if upload:

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


            last_raw = current_raw


            print(
                f"✅ Data inserted into DB at {timestamp}",
                flush=True
            )


        else:

            print(
                "⏭ No significant pressure change → "
                "Skipped insert",
                flush=True
            )


        time.sleep(
            READ_INTERVAL
        )


except KeyboardInterrupt:

    print(
        "\n🛑 Capture stopped",
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