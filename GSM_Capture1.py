#!/usr/bin/env python3

import time
import sys
import sqlite3
import os
import re
import serial
import threading


# ============================================================
# ENCODING
# ============================================================

sys.stdout.reconfigure(encoding="utf-8")


# ============================================================
# CONFIGURATION
# ============================================================

RAW_THRESHOLD = 326          # ~0.5 bar equivalent
READ_INTERVAL = 0.1          # pressure sampling interval

GSM_INTERVAL = 30            # GSM information refresh
GNSS_INTERVAL = 5             # GNSS polling interval

EC200U_PORT = "/dev/ttyAMA3"
EC200U_BAUD = 115200

MODEM_RETRY_INTERVAL = 5


# ============================================================
# DATABASE PATH
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DB_PATH = os.path.join(
    BASE_DIR,
    "db",
    "new_db.db"
)


# ============================================================
# GLOBAL EC200U
# ============================================================

gsm_serial = None

gsm_lock = threading.Lock()

gsm_connected = False

last_modem_retry = 0


# ============================================================
# GSM INFORMATION
# ============================================================

gsm_info = {
    "gsm_status": "DISCONNECTED",
    "sim_status": None,
    "sim_iccid": None,
    "mobile_number": None,
    "signal_strength": None,
    "signal_dbm": None,
    "network_status": None,
    "operator": None,
    "latency_ms": None,
}


# ============================================================
# GNSS INFORMATION
# ============================================================

gnss_info = {
    "gnss_status": "NO FIX",
    "latitude": None,
    "longitude": None,
    "altitude_m": None,
    "satellites": None,
    "gps_utc": None,
}


# ============================================================
# DATABASE CONNECTION
# ============================================================

def get_db_connection():

    os.makedirs(
        os.path.dirname(DB_PATH),
        exist_ok=True
    )

    connection = sqlite3.connect(
        DB_PATH,
        timeout=30,
        check_same_thread=False
    )

    connection.row_factory = sqlite3.Row

    connection.execute(
        "PRAGMA journal_mode=WAL"
    )

    connection.execute(
        "PRAGMA busy_timeout=30000"
    )

    return connection


# ============================================================
# DATABASE INITIALIZATION
# ============================================================

def initialize_database():

    conn = get_db_connection()

    try:

        # ----------------------------------------------------
        # Original pressure columns
        # + GSM columns
        # + GNSS columns
        #
        # TOTAL = 23 COLUMNS
        # ----------------------------------------------------

        conn.execute("""
            CREATE TABLE IF NOT EXISTS brake_pressure_log (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                device_id TEXT,

                BP_raw INTEGER,
                FP_raw INTEGER,
                CR_raw INTEGER,
                BC_raw INTEGER,

                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,

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

        # ----------------------------------------------------
        # CHECK EXISTING DATABASE COLUMNS
        # ----------------------------------------------------

        existing_columns = set()

        rows = conn.execute(
            "PRAGMA table_info(brake_pressure_log)"
        ).fetchall()

        for row in rows:

            existing_columns.add(
                row["name"]
            )

        # ----------------------------------------------------
        # ADD MISSING COLUMNS
        # ----------------------------------------------------

        required_columns = {

            "device_id": "TEXT",

            "BP_raw": "INTEGER",
            "FP_raw": "INTEGER",
            "CR_raw": "INTEGER",
            "BC_raw": "INTEGER",

            "timestamp": "DATETIME",

            "uploaded": "INTEGER DEFAULT 0",

            "gsm_status": "TEXT",
            "sim_status": "TEXT",
            "sim_iccid": "TEXT",
            "mobile_number": "TEXT",
            "signal_strength": "INTEGER",
            "signal_dbm": "INTEGER",
            "network_status": "TEXT",
            "operator": "TEXT",
            "latency_ms": "REAL",

            "gnss_status": "TEXT",
            "latitude": "REAL",
            "longitude": "REAL",
            "altitude_m": "REAL",
            "satellites": "INTEGER",
            "gps_utc": "TEXT"
        }

        for column, datatype in required_columns.items():

            if column not in existing_columns:

                print(
                    f"🛠 Adding DB column: {column}",
                    flush=True
                )

                conn.execute(
                    f"""
                    ALTER TABLE brake_pressure_log
                    ADD COLUMN {column} {datatype}
                    """
                )

        conn.commit()

    finally:

        conn.close()


# ============================================================
# FETCH DEVICE ID
# ============================================================

def get_device_id():

    conn = get_db_connection()

    try:

        cursor = conn.cursor()

        cursor.execute(
            "SELECT device_id FROM device_config LIMIT 1"
        )

        row = cursor.fetchone()

        if row and row["device_id"]:

            return row["device_id"]

        return "UNKNOWN"

    except Exception as e:

        print(
            f"⚠️ Device ID read error: {e}",
            flush=True
        )

        return "UNKNOWN"

    finally:

        conn.close()


# ============================================================
# DEVICE ID
# ============================================================

DEVICE_ID = get_device_id()

print()
print("=" * 75)
print(
    f"✅ Device ID = {DEVICE_ID}",
    flush=True
)
print("=" * 75)


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

    # IMPORTANT:
    # Your installed library works with numeric channels.
    bp_channel = AnalogIn(ads, 0)
    fp_channel = AnalogIn(ads, 1)
    cr_channel = AnalogIn(ads, 2)
    bc_channel = AnalogIn(ads, 3)

    print(
        "✅ ADS1115 initialized",
        flush=True
    )

except Exception as e:

    ADS_AVAILABLE = False

    print(
        "❌ ADS1115 initialization failed",
        flush=True
    )

    print(
        f"Error: {e}",
        flush=True
    )


# ============================================================
# READ ADS1115
# ============================================================

def read_raw_values():

    if not ADS_AVAILABLE:

        return (
            0,
            0,
            0,
            0
        )

    try:

        return (
            int(bp_channel.value),
            int(fp_channel.value),
            int(cr_channel.value),
            int(bc_channel.value)
        )

    except Exception as e:

        print(
            f"⚠️ ADS1115 read error: {e}",
            flush=True
        )

        return (
            0,
            0,
            0,
            0
        )


# ============================================================
# EC200U SEND AT COMMAND
# ============================================================

def send_at(
    command,
    timeout=3
):

    global gsm_serial
    global gsm_connected

    if gsm_serial is None:

        return ""

    try:

        with gsm_lock:

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

                    if (
                        "\r\nOK\r\n" in response
                        or "\r\nERROR\r\n" in response
                    ):

                        break

                time.sleep(0.05)

            return response

    except Exception as e:

        print(
            f"⚠️ EC200U UART error: {e}",
            flush=True
        )

        gsm_connected = False

        return ""


# ============================================================
# OPEN EC200U
# ============================================================

def open_ec200u():

    global gsm_serial
    global gsm_connected

    try:

        if gsm_serial is not None:

            try:
                gsm_serial.close()
            except Exception:
                pass

            gsm_serial = None

        gsm_serial = serial.Serial(
            EC200U_PORT,
            EC200U_BAUD,
            timeout=2,
            write_timeout=2
        )

        time.sleep(1)

        print()
        print(
            f"🔌 EC200U UART opened: "
            f"{EC200U_PORT}",
            flush=True
        )

        response = send_at(
            "AT",
            timeout=3
        )

        if "OK" in response:

            gsm_connected = True

            gsm_info[
                "gsm_status"
            ] = "Connected"

            print(
                "✅ EC200U responding",
                flush=True
            )

            return True

        print(
            "❌ EC200U not responding",
            flush=True
        )

    except Exception as e:

        print(
            f"❌ EC200U connection failed: {e}",
            flush=True
        )

    gsm_connected = False

    gsm_info[
        "gsm_status"
    ] = "DISCONNECTED"

    return False


# ============================================================
# CLOSE EC200U
# ============================================================

def close_ec200u():

    global gsm_serial
    global gsm_connected

    try:

        if gsm_serial is not None:

            gsm_serial.close()

    except Exception:
        pass

    gsm_serial = None

    gsm_connected = False

    gsm_info[
        "gsm_status"
    ] = "DISCONNECTED"


# ============================================================
# CHECK EC200U
# ============================================================

def check_ec200u():

    global gsm_connected

    if gsm_serial is None:

        return False

    response = send_at(
        "AT",
        timeout=2
    )

    if "OK" in response:

        gsm_connected = True

        gsm_info[
            "gsm_status"
        ] = "Connected"

        return True

    gsm_connected = False

    return False


# ============================================================
# ENSURE EC200U CONNECTION
# ============================================================

def ensure_ec200u():

    global last_modem_retry

    if check_ec200u():

        return True

    now = time.time()

    if (
        now - last_modem_retry
        < MODEM_RETRY_INTERVAL
    ):

        return False

    last_modem_retry = now

    print()
    print(
        "⚠️ EC200U disconnected",
        flush=True
    )

    print(
        "🔄 Trying automatic EC200U reconnect...",
        flush=True
    )

    close_ec200u()

    return open_ec200u()


# ============================================================
# UPDATE GSM INFORMATION
# ============================================================

def update_gsm_information():

    if not ensure_ec200u():

        gsm_info[
            "gsm_status"
        ] = "DISCONNECTED"

        return

    # --------------------------------------------------------
    # SIM
    # --------------------------------------------------------

    cpin = send_at(
        "AT+CPIN?",
        timeout=3
    )

    if "READY" in cpin:

        gsm_info[
            "sim_status"
        ] = "READY"

    else:

        gsm_info[
            "sim_status"
        ] = "NOT READY"

    # --------------------------------------------------------
    # ICCID
    # --------------------------------------------------------

    qccid = send_at(
        "AT+QCCID",
        timeout=3
    )

    match = re.search(
        r"\+QCCID:\s*([0-9]+)",
        qccid
    )

    if match:

        gsm_info[
            "sim_iccid"
        ] = match.group(1)

    # --------------------------------------------------------
    # MOBILE NUMBER
    # --------------------------------------------------------

    cnum = send_at(
        "AT+CNUM",
        timeout=3
    )

    match = re.search(
        r'\+CNUM:\s*"[^"]*","([^"]+)"',
        cnum
    )

    if match:

        gsm_info[
            "mobile_number"
        ] = match.group(1)

    # --------------------------------------------------------
    # SIGNAL
    # --------------------------------------------------------

    csq = send_at(
        "AT+CSQ",
        timeout=3
    )

    match = re.search(
        r"\+CSQ:\s*(\d+),",
        csq
    )

    if match:

        rssi = int(
            match.group(1)
        )

        gsm_info[
            "signal_strength"
        ] = rssi

        if 0 <= rssi <= 31:

            gsm_info[
                "signal_dbm"
            ] = -113 + (
                2 * rssi
            )

        else:

            gsm_info[
                "signal_dbm"
            ] = None

    # --------------------------------------------------------
    # NETWORK
    # --------------------------------------------------------

    creg = send_at(
        "AT+CREG?",
        timeout=3
    )

    match = re.search(
        r"\+CREG:\s*\d+,(\d+)",
        creg
    )

    if match:

        registration = int(
            match.group(1)
        )

        if registration in (
            1,
            5
        ):

            gsm_info[
                "network_status"
            ] = "REGISTERED"

        else:

            gsm_info[
                "network_status"
            ] = "NOT REGISTERED"

    # --------------------------------------------------------
    # OPERATOR
    # --------------------------------------------------------

    cops = send_at(
        "AT+COPS?",
        timeout=5
    )

    match = re.search(
        r'\+COPS:\s*\d+,\d+,"([^"]+)"',
        cops
    )

    if match:

        gsm_info[
            "operator"
        ] = match.group(1)

    # --------------------------------------------------------
    # LATENCY
    # --------------------------------------------------------

    ping_response = send_at(
        'AT+QPING=1,"8.8.8.8",5,1',
        timeout=10
    )

    # Examples can contain:
    # time=8.01 ms
    # time=8.01
    # time: 8.01

    match = re.search(
        r"time[=:]\s*([0-9.]+)",
        ping_response,
        re.IGNORECASE
    )

    if match:

        gsm_info[
            "latency_ms"
        ] = float(
            match.group(1)
        )

    else:

        gsm_info[
            "latency_ms"
        ] = None

    gsm_info[
        "gsm_status"
    ] = "Connected"


# ============================================================
# PRINT GSM INFORMATION
# ONLY CALLED ONCE AT STARTUP
# ============================================================

def print_gsm_information():

    print()
    print("📡 GSM INFORMATION")

    print(
        f"   GSM Status    : "
        f"{gsm_info['gsm_status']}"
    )

    print(
        f"   SIM Status    : "
        f"{gsm_info['sim_status']}"
    )

    print(
        f"   ICCID         : "
        f"{gsm_info['sim_iccid']}"
    )

    print(
        f"   Mobile Number : "
        f"{gsm_info['mobile_number']}"
    )

    print(
        f"   Signal RSSI   : "
        f"{gsm_info['signal_strength']}"
    )

    print(
        f"   Signal dBm    : "
        f"{gsm_info['signal_dbm']}"
    )

    print(
        f"   Network       : "
        f"{gsm_info['network_status']}"
    )

    print(
        f"   Operator      : "
        f"{gsm_info['operator']}"
    )

    print(
        f"   Latency       : "
        f"{gsm_info['latency_ms']} ms"
    )


# ============================================================
# START / CHECK GNSS
# ============================================================

def start_gnss():

    if not ensure_ec200u():

        return False

    status = send_at(
        "AT+QGPS?",
        timeout=3
    )

    if "+QGPS: 1" in status:

        print(
            "🛰️✅ GNSS already enabled",
            flush=True
        )

        return True

    print(
        "🛰️ Starting GNSS...",
        flush=True
    )

    response = send_at(
        "AT+QGPS=1",
        timeout=5
    )

    if "OK" in response:

        print(
            "🛰️✅ GNSS enabled",
            flush=True
        )

        return True

    # Check once again
    status = send_at(
        "AT+QGPS?",
        timeout=3
    )

    if "+QGPS: 1" in status:

        print(
            "🛰️✅ GNSS already enabled",
            flush=True
        )

        return True

    print(
        "❌ GNSS could not be enabled",
        flush=True
    )

    return False


# ============================================================
# SATELLITE COUNT
# ============================================================

def get_satellite_count():

    if not ensure_ec200u():

        return None

    response = send_at(
        'AT+QGPSGNMEA="GGA"',
        timeout=3
    )

    for line in response.splitlines():

        line = line.strip()

        if (
            line.startswith("$GPGGA")
            or line.startswith("$GNGGA")
        ):

            fields = line.split(",")

            try:

                # GGA:
                # index 7 = satellites

                if len(fields) > 7:

                    return int(
                        fields[7]
                    )

            except Exception:
                pass

    return None


# ============================================================
# READ GNSS
# ============================================================

def read_gnss():

    if not ensure_ec200u():

        gnss_info[
            "gnss_status"
        ] = "NO FIX"

        return False

    # --------------------------------------------------------
    # Make sure GNSS is enabled
    # --------------------------------------------------------

    status = send_at(
        "AT+QGPS?",
        timeout=3
    )

    if "+QGPS: 1" not in status:

        print(
            "⚠️ GNSS disabled",
            flush=True
        )

        print(
            "🔄 Restarting GNSS...",
            flush=True
        )

        if not start_gnss():

            gnss_info[
                "gnss_status"
            ] = "NO FIX"

            return False

    # --------------------------------------------------------
    # Get GPS location
    # --------------------------------------------------------

    response = send_at(
        "AT+QGPSLOC=0",
        timeout=5
    )

    match = re.search(
        r"\+QGPSLOC:\s*([^\r\n]+)",
        response
    )

    if not match:

        gnss_info[
            "gnss_status"
        ] = "NO FIX"

        return False

    values = [
        value.strip()
        for value in
        match.group(1).split(",")
    ]

    try:

        if len(values) < 5:

            gnss_info[
                "gnss_status"
            ] = "NO FIX"

            return False

        gps_utc = values[0]

        latitude = float(
            values[1]
        )

        longitude = float(
            values[2]
        )

        altitude = float(
            values[4]
        )

        # ----------------------------------------------------
        # Invalid coordinates
        # ----------------------------------------------------

        if (
            abs(latitude) < 0.000001
            and abs(longitude) < 0.000001
        ):

            gnss_info[
                "gnss_status"
            ] = "NO FIX"

            return False

        satellites = get_satellite_count()

        gnss_info[
            "gnss_status"
        ] = "FIX"

        gnss_info[
            "latitude"
        ] = latitude

        gnss_info[
            "longitude"
        ] = longitude

        gnss_info[
            "altitude_m"
        ] = altitude

        gnss_info[
            "satellites"
        ] = satellites

        gnss_info[
            "gps_utc"
        ] = gps_utc

        return True

    except Exception:

        gnss_info[
            "gnss_status"
        ] = "NO FIX"

        return False


# ============================================================
# PRINT GNSS + CURRENT PRESSURE
# ============================================================

def print_capture_status(
    current_raw
):

    timestamp = time.strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    print()

    print(
        f"device_id={DEVICE_ID}, "
        f"BP_raw={current_raw[0]}, "
        f"FP_raw={current_raw[1]}, "
        f"CR_raw={current_raw[2]}, "
        f"BC_raw={current_raw[3]}, "
        f"GNSS={gnss_info['gnss_status']}, "
        f"LAT={gnss_info['latitude']}, "
        f"LON={gnss_info['longitude']}, "
        f"ALT={gnss_info['altitude_m']}, "
        f"SAT={gnss_info['satellites']}, "
        f"Timestamp={timestamp}, "
        f"GSM={gsm_info['gsm_status']}, "
        f"RSSI={gsm_info['signal_strength']}, "
        f"dBm={gsm_info['signal_dbm']}, "
        f"Latency={gsm_info['latency_ms']} ms",
        flush=True
    )


# ============================================================
# DATABASE INSERT
# ============================================================

def insert_record(
    current_raw,
    record_type
):

    timestamp = time.strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    bp = int(current_raw[0])
    fp = int(current_raw[1])
    cr = int(current_raw[2])
    bc = int(current_raw[3])

    conn = None

    try:

        conn = get_db_connection()

        # ----------------------------------------------------
        # EXACTLY 23 COLUMNS
        # ----------------------------------------------------

        sql = """
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
        """

        # ----------------------------------------------------
        # EXACTLY 22 VALUES FOR THE 22 NON-ID COLUMNS
        #
        # SQLite generates id automatically.
        # ----------------------------------------------------

        values = (
            DEVICE_ID,

            bp,
            fp,
            cr,
            bc,

            timestamp,
            0,

            gsm_info["gsm_status"],
            gsm_info["sim_status"],
            gsm_info["sim_iccid"],
            gsm_info["mobile_number"],
            gsm_info["signal_strength"],
            gsm_info["signal_dbm"],
            gsm_info["network_status"],
            gsm_info["operator"],
            gsm_info["latency_ms"],

            gnss_info["gnss_status"],
            gnss_info["latitude"],
            gnss_info["longitude"],
            gnss_info["altitude_m"],
            gnss_info["satellites"],
            gnss_info["gps_utc"]
        )

        cursor = conn.cursor()

        cursor.execute(
            sql,
            values
        )

        conn.commit()

        db_id = cursor.lastrowid

        # ----------------------------------------------------
        # GNSS INSERT
        # ----------------------------------------------------

        if record_type == "GNSS":

            print()
            print(
                "🛰️📥 FIRST GNSS FIX STORED",
                flush=True
            )

            print(
                f"   DB ID       : {db_id}",
                flush=True
            )

            print(
                f"   Latitude    : "
                f"{gnss_info['latitude']}",
                flush=True
            )

            print(
                f"   Longitude   : "
                f"{gnss_info['longitude']}",
                flush=True
            )

            print(
                f"   Altitude    : "
                f"{gnss_info['altitude_m']} m",
                flush=True
            )

            print(
                f"   Satellites  : "
                f"{gnss_info['satellites']}",
                flush=True
            )

        # ----------------------------------------------------
        # PRESSURE INSERT
        # ----------------------------------------------------

        else:

            print()
            print(
                "💾 PRESSURE DATA STORED",
                flush=True
            )

            print(
                f"   DB ID       : {db_id}",
                flush=True
            )

            print(
                f"   BP_raw      : {bp}",
                flush=True
            )

            print(
                f"   FP_raw      : {fp}",
                flush=True
            )

            print(
                f"   CR_raw      : {cr}",
                flush=True
            )

            print(
                f"   BC_raw      : {bc}",
                flush=True
            )

            print(
                f"   GSM Status  : "
                f"{gsm_info['gsm_status']}",
                flush=True
            )

            print(
                f"   RSSI        : "
                f"{gsm_info['signal_strength']}",
                flush=True
            )

            print(
                f"   Signal dBm  : "
                f"{gsm_info['signal_dbm']}",
                flush=True
            )

            print(
                f"   Latency     : "
                f"{gsm_info['latency_ms']} ms",
                flush=True
            )

            print(
                f"   GNSS        : "
                f"{gnss_info['gnss_status']}",
                flush=True
            )

            print(
                f"   LAT         : "
                f"{gnss_info['latitude']}",
                flush=True
            )

            print(
                f"   LON         : "
                f"{gnss_info['longitude']}",
                flush=True
            )

            print(
                f"   SAT         : "
                f"{gnss_info['satellites']}",
                flush=True
            )

            print(
                f"   Timestamp   : "
                f"{timestamp}",
                flush=True
            )

        return True

    except Exception as e:

        print()
        print(
            "❌ DATABASE INSERT FAILED",
            flush=True
        )

        print(
            f"Error: {e}",
            flush=True
        )

        return False

    finally:

        if conn:

            conn.close()


# ============================================================
# MAIN
# ============================================================

def main():

    global last_raw

    global first_pressure_stored
    global first_gnss_fix_stored

    global last_gsm_update
    global last_gnss_update

    # --------------------------------------------------------
    # DATABASE
    # --------------------------------------------------------

    initialize_database()

    # --------------------------------------------------------
    # ADS STATUS
    # --------------------------------------------------------

    print()

    if not ADS_AVAILABLE:

        print(
            "⚠️ ADS1115 sensor not detected!",
            flush=True
        )

    # --------------------------------------------------------
    # EC200U
    # --------------------------------------------------------

    print()
    print(
        "🔌 Initializing EC200U...",
        flush=True
    )

    modem_ok = open_ec200u()

    if modem_ok:

        print(
            "🛰️ Starting / checking GNSS...",
            flush=True
        )

        start_gnss()

    else:

        print(
            "⚠️ EC200U unavailable",
            flush=True
        )

        print(
            "⚠️ Pressure logging will continue",
            flush=True
        )

    # --------------------------------------------------------
    # INITIAL GSM INFORMATION
    # --------------------------------------------------------

    print()

    print(
        "📡 Updating GSM information...",
        flush=True
    )

    update_gsm_information()

    # --------------------------------------------------------
    # GSM INFORMATION SHOWN ONLY ONCE
    # --------------------------------------------------------

    print_gsm_information()

    # --------------------------------------------------------
    # START
    # --------------------------------------------------------

    print()
    print("=" * 75)
    print(
        "🚀 Capture system started",
        flush=True
    )
    print("=" * 75)

    print(
        f"📊 RAW_THRESHOLD = {RAW_THRESHOLD}",
        flush=True
    )

    print(
        f"⏱ READ_INTERVAL = {READ_INTERVAL} sec",
        flush=True
    )

    print(
        f"📡 GSM interval = {GSM_INTERVAL} sec",
        flush=True
    )

    print(
        f"🛰️ GNSS interval = {GNSS_INTERVAL} sec",
        flush=True
    )

    print()
    print("📌 DATABASE LOGIC")

    print(
        "1. First pressure reading → STORE",
        flush=True
    )

    print(
        "2. First GNSS FIX → STORE ONE additional record",
        flush=True
    )

    print(
        "3. GPS polling without pressure change → SKIP",
        flush=True
    )

    print(
        "4. Any pressure difference >= 326 → STORE ALL 4 readings",
        flush=True
    )

    print(
        "5. Pressure difference < 326 → SKIP",
        flush=True
    )

    print(
        "6. GPS-only record does NOT change last_raw",
        flush=True
    )

    print(
        "7. GSM disconnect → automatic reconnect",
        flush=True
    )

    print(
        "8. EC200U recovery → GNSS automatically checked/restarted",
        flush=True
    )

    print(
        "9. Pressure logging continues if GSM is offline",
        flush=True
    )

    print("=" * 75)

    # --------------------------------------------------------
    # TIMERS
    # --------------------------------------------------------

    last_gsm_update = time.time()

    last_gnss_update = time.time()

    # --------------------------------------------------------
    # MAIN LOOP
    # --------------------------------------------------------

    try:

        while True:

            now = time.time()

            # =================================================
            # GSM INFORMATION
            # =================================================

            if (
                now - last_gsm_update
                >= GSM_INTERVAL
            ):

                # ------------------------------------------------
                # Update silently.
                # Do NOT print the complete GSM block again.
                # ------------------------------------------------

                update_gsm_information()

                last_gsm_update = now

            # =================================================
            # GNSS
            # =================================================

            if (
                now - last_gnss_update
                >= GNSS_INTERVAL
            ):

                print()
                print(
                    "🛰️ Checking GNSS...",
                    flush=True
                )

                gps_fix = read_gnss()

                if gps_fix:

                    print(
                        f"📍 GNSS FIX | "
                        f"LAT={gnss_info['latitude']} | "
                        f"LON={gnss_info['longitude']} | "
                        f"ALT={gnss_info['altitude_m']} m | "
                        f"SAT={gnss_info['satellites']}",
                        flush=True
                    )

                else:

                    print(
                        "🛰️ GNSS: NO FIX",
                        flush=True
                    )

                last_gnss_update = now

            # =================================================
            # PRESSURE
            # =================================================

            current_raw = read_raw_values()

            # -------------------------------------------------
            # FIRST PRESSURE READING
            # -------------------------------------------------

            if not first_pressure_stored:

                print()
                print(
                    "📌 FIRST PRESSURE READING",
                    flush=True
                )

                print(
                    f"   BP = {current_raw[0]}",
                    flush=True
                )

                print(
                    f"   FP = {current_raw[1]}",
                    flush=True
                )

                print(
                    f"   CR = {current_raw[2]}",
                    flush=True
                )

                print(
                    f"   BC = {current_raw[3]}",
                    flush=True
                )

                # ---------------------------------------------
                # STORE FIRST PRESSURE
                # ---------------------------------------------

                success = insert_record(
                    current_raw,
                    "PRESSURE"
                )

                if success:

                    first_pressure_stored = True

                    # IMPORTANT:
                    # Only pressure insert changes last_raw.

                    last_raw = current_raw

                time.sleep(
                    READ_INTERVAL
                )

                continue

            # =================================================
            # FIRST GNSS FIX
            # =================================================

            if (
                not first_gnss_fix_stored
                and
                gnss_info["gnss_status"] == "FIX"
            ):

                print()
                print(
                    "🛰️✅ FIRST GNSS FIX RECEIVED",
                    flush=True
                )

                print(
                    "📥 One GNSS record will be stored in SQLite",
                    flush=True
                )

                print(
                    f"📍 GNSS FIX | "
                    f"LAT={gnss_info['latitude']} | "
                    f"LON={gnss_info['longitude']} | "
                    f"ALT={gnss_info['altitude_m']} m | "
                    f"SAT={gnss_info['satellites']}",
                    flush=True
                )

                # ------------------------------------------------
                # Show complete record before insertion
                # ------------------------------------------------

                print_capture_status(
                    current_raw
                )

                # ------------------------------------------------
                # STORE GNSS RECORD
                # ------------------------------------------------

                success = insert_record(
                    current_raw,
                    "GNSS"
                )

                if success:

                    first_gnss_fix_stored = True

                    # IMPORTANT:
                    # DO NOT CHANGE last_raw HERE.
                    #
                    # GPS-only insertion must not affect
                    # pressure threshold calculation.

                time.sleep(
                    READ_INTERVAL
                )

                continue

            # =================================================
            # PRESSURE CHANGE CHECK
            # =================================================

            bp_diff = abs(
                current_raw[0] - last_raw[0]
            )

            fp_diff = abs(
                current_raw[1] - last_raw[1]
            )

            cr_diff = abs(
                current_raw[2] - last_raw[2]
            )

            bc_diff = abs(
                current_raw[3] - last_raw[3]
            )

            # =================================================
            # SIGNIFICANT PRESSURE CHANGE
            # =================================================

            if (
                bp_diff >= RAW_THRESHOLD
                or
                fp_diff >= RAW_THRESHOLD
                or
                cr_diff >= RAW_THRESHOLD
                or
                bc_diff >= RAW_THRESHOLD
            ):

                print()
                print(
                    "⚠️ PRESSURE CHANGE DETECTED",
                    flush=True
                )

                print(
                    f"   BP difference = {bp_diff}",
                    flush=True
                )

                print(
                    f"   FP difference = {fp_diff}",
                    flush=True
                )

                print(
                    f"   CR difference = {cr_diff}",
                    flush=True
                )

                print(
                    f"   BC difference = {bc_diff}",
                    flush=True
                )

                print_capture_status(
                    current_raw
                )

                # ------------------------------------------------
                # STORE ALL FOUR PRESSURES
                # ------------------------------------------------

                success = insert_record(
                    current_raw,
                    "PRESSURE"
                )

                if success:

                    # IMPORTANT:
                    # last_raw changes ONLY after successful
                    # pressure DB insertion.

                    last_raw = current_raw

            # =================================================
            # NO SIGNIFICANT CHANGE
            # =================================================

            # Do not print every 0.1 second.
            # This prevents SSH from being flooded.

            time.sleep(
                READ_INTERVAL
            )

    except KeyboardInterrupt:

        print()
        print()
        print(
            "🛑 Capture system stopped",
            flush=True
        )

    finally:

        close_ec200u()


# ============================================================
# PROGRAM START
# ============================================================

if __name__ == "__main__":

    main()