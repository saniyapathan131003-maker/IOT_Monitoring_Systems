#!/usr/bin/env python3

import os
import re
import time
import sqlite3
import threading
from datetime import datetime

import board
import busio
import serial

import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn


# ============================================================
# CONFIGURATION
# ============================================================

DEVICE_ID = "Raspberry4_8"

DB_PATH = "db/new_db.db"

GSM_PORT = "/dev/ttyAMA3"
GSM_BAUD = 115200

RAW_THRESHOLD = 326

READ_INTERVAL = 0.1
GSM_INTERVAL = 30
GNSS_INTERVAL = 5

MODEM_RETRY_INTERVAL = 5

ADS_ADDRESS = 0x48

# ------------------------------------------------------------
# AWS / uploader will use uploaded field.
# 0 = not uploaded
# 1 = uploaded
# ------------------------------------------------------------


# ============================================================
# GLOBAL VARIABLES
# ============================================================

gsm_serial = None
gsm_lock = threading.Lock()

gsm_connected = False
gnss_enabled = False

last_gsm_update = 0
last_gnss_update = 0

first_pressure_stored = False
first_gnss_fix_stored = False

last_raw = None

latest_gsm = {
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

latest_gnss = {
    "gnss_status": "NO FIX",
    "latitude": None,
    "longitude": None,
    "altitude_m": None,
    "satellites": None,
    "gps_utc": None,
}


# ============================================================
# START MESSAGE
# ============================================================

print()
print("=" * 75)
print(f"✅ Device ID = {DEVICE_ID}")
print("=" * 75)


# ============================================================
# DATABASE
# ============================================================

def get_db_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    conn = sqlite3.connect(
        DB_PATH,
        timeout=30,
        check_same_thread=False
    )

    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")

    return conn


def initialize_database():

    conn = get_db_connection()

    try:

        # ----------------------------------------------------
        # Create base table if it does not exist
        # ----------------------------------------------------

        conn.execute("""
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

        # ----------------------------------------------------
        # IMPORTANT:
        # Existing DB may have older schema.
        # Add missing columns automatically.
        # ----------------------------------------------------

        required_columns = {
            "device_id": "TEXT",
            "BP_raw": "INTEGER",
            "FP_raw": "INTEGER",
            "CR_raw": "INTEGER",
            "BC_raw": "INTEGER",
            "timestamp": "TEXT",
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
            "gps_utc": "TEXT",
        }

        existing = set()

        rows = conn.execute(
            "PRAGMA table_info(brake_pressure_log)"
        ).fetchall()

        for row in rows:
            existing.add(row[1])

        for column, datatype in required_columns.items():

            if column not in existing:

                print(f"🛠 Adding missing DB column: {column}")

                conn.execute(
                    f"ALTER TABLE brake_pressure_log "
                    f"ADD COLUMN {column} {datatype}"
                )

        conn.commit()

        print("✅ SQLite database initialized")

    except Exception as e:

        print("❌ DATABASE INITIALIZATION FAILED")
        print(f"Error: {e}")

        raise

    finally:
        conn.close()


# ============================================================
# DATABASE INSERT
# ============================================================

def insert_database_record(
    bp,
    fp,
    cr,
    bc,
    record_type="PRESSURE"
):

    timestamp = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    # --------------------------------------------------------
    # Build values using dictionary.
    # This prevents column/value count mismatch.
    # --------------------------------------------------------

    data = {

        "device_id": DEVICE_ID,

        "BP_raw": int(bp),
        "FP_raw": int(fp),
        "CR_raw": int(cr),
        "BC_raw": int(bc),

        "timestamp": timestamp,

        "uploaded": 0,

        "gsm_status": latest_gsm["gsm_status"],
        "sim_status": latest_gsm["sim_status"],
        "sim_iccid": latest_gsm["sim_iccid"],
        "mobile_number": latest_gsm["mobile_number"],
        "signal_strength": latest_gsm["signal_strength"],
        "signal_dbm": latest_gsm["signal_dbm"],
        "network_status": latest_gsm["network_status"],
        "operator": latest_gsm["operator"],
        "latency_ms": latest_gsm["latency_ms"],

        "gnss_status": latest_gnss["gnss_status"],
        "latitude": latest_gnss["latitude"],
        "longitude": latest_gnss["longitude"],
        "altitude_m": latest_gnss["altitude_m"],
        "satellites": latest_gnss["satellites"],
        "gps_utc": latest_gnss["gps_utc"],
    }

    conn = None

    try:

        conn = get_db_connection()

        columns = list(data.keys())

        placeholders = ",".join(
            ["?"] * len(columns)
        )

        sql = f"""
            INSERT INTO brake_pressure_log
            ({",".join(columns)})
            VALUES
            ({placeholders})
        """

        values = [data[column] for column in columns]

        cursor = conn.execute(sql, values)

        conn.commit()

        db_id = cursor.lastrowid

        if record_type == "GNSS":

            print()
            print("🛰️📥 FIRST GNSS FIX STORED")
            print(f"   DB ID       : {db_id}")
            print(
                f"   Latitude    : "
                f"{latest_gnss['latitude']}"
            )
            print(
                f"   Longitude   : "
                f"{latest_gnss['longitude']}"
            )
            print(
                f"   Altitude    : "
                f"{latest_gnss['altitude_m']} m"
            )
            print(
                f"   Satellites  : "
                f"{latest_gnss['satellites']}"
            )

        else:

            print()
            print("💾 PRESSURE RECORD STORED")
            print(f"   DB ID : {db_id}")
            print(f"   BP    : {bp}")
            print(f"   FP    : {fp}")
            print(f"   CR    : {cr}")
            print(f"   BC    : {bc}")

        return True

    except Exception as e:

        print()
        print("❌ DATABASE INSERT FAILED")
        print(f"Error: {e}")

        return False

    finally:

        if conn:
            conn.close()


# ============================================================
# ADS1115
# ============================================================

ads = None

BP_channel = None
FP_channel = None
CR_channel = None
BC_channel = None


def initialize_ads():

    global ads
    global BP_channel
    global FP_channel
    global CR_channel
    global BC_channel

    try:

        i2c = busio.I2C(
            board.SCL,
            board.SDA
        )

        ads = ADS.ADS1115(
            i2c,
            address=ADS_ADDRESS
        )

        # ----------------------------------------------------
        # IMPORTANT:
        # Your installed library does NOT expose ADS.P0.
        # Numeric channels 0,1,2,3 work with your version.
        # ----------------------------------------------------

        BP_channel = AnalogIn(ads, 0)
        FP_channel = AnalogIn(ads, 1)
        CR_channel = AnalogIn(ads, 2)
        BC_channel = AnalogIn(ads, 3)

        print("✅ ADS1115 initialized")

        return True

    except Exception as e:

        print("❌ ADS1115 initialization failed")
        print(f"Error: {e}")

        return False


def read_pressure():

    try:

        bp = BP_channel.value
        fp = FP_channel.value
        cr = CR_channel.value
        bc = BC_channel.value

        return (
            int(bp),
            int(fp),
            int(cr),
            int(bc)
        )

    except Exception as e:

        print(f"❌ ADS1115 read error: {e}")

        return None


# ============================================================
# EC200U UART
# ============================================================

def close_gsm():

    global gsm_serial
    global gsm_connected
    global gnss_enabled

    try:

        if gsm_serial:

            gsm_serial.close()

    except Exception:
        pass

    gsm_serial = None
    gsm_connected = False
    gnss_enabled = False

    latest_gsm["gsm_status"] = "DISCONNECTED"


def open_gsm():

    global gsm_serial
    global gsm_connected

    try:

        gsm_serial = serial.Serial(
            GSM_PORT,
            GSM_BAUD,
            timeout=2,
            write_timeout=2
        )

        time.sleep(1)

        print()
        print(
            f"🔌 EC200U UART opened: "
            f"{GSM_PORT}"
        )

        response = send_at(
            "AT",
            timeout=3,
            show=False
        )

        if "OK" in response:

            gsm_connected = True

            latest_gsm["gsm_status"] = "Connected"

            print("✅ EC200U responding")

            return True

        print("❌ EC200U not responding")

        close_gsm()

        return False

    except Exception as e:

        print(
            f"❌ EC200U UART open failed: {e}"
        )

        close_gsm()

        return False


def send_at(command, timeout=3, show=False):

    global gsm_serial

    if gsm_serial is None:
        return ""

    try:

        with gsm_lock:

            gsm_serial.reset_input_buffer()

            gsm_serial.write(
                (command + "\r\n").encode()
            )

            gsm_serial.flush()

            start = time.time()

            response = ""

            while (
                time.time() - start
            ) < timeout:

                if gsm_serial.in_waiting:

                    data = gsm_serial.read(
                        gsm_serial.in_waiting
                    ).decode(
                        errors="ignore"
                    )

                    response += data

                    if (
                        "\r\nOK\r\n" in response
                        or "\r\nERROR\r\n" in response
                    ):
                        break

                time.sleep(0.05)

            if show:

                print(f">>> {command}")
                print(response.strip())

            return response

    except Exception as e:

        print(
            f"❌ UART error for {command}: {e}"
        )

        close_gsm()

        return ""


def ensure_modem():

    global gsm_connected

    if gsm_serial is None:

        return open_gsm()

    response = send_at(
        "AT",
        timeout=2,
        show=False
    )

    if "OK" in response:

        gsm_connected = True
        latest_gsm["gsm_status"] = "Connected"

        return True

    print()
    print("⚠️ EC200U not responding")
    print("🔄 Starting automatic recovery...")

    close_gsm()

    time.sleep(
        MODEM_RETRY_INTERVAL
    )

    return open_gsm()


# ============================================================
# GSM INFORMATION
# ============================================================

def update_gsm_information():

    if not ensure_modem():

        latest_gsm["gsm_status"] = "DISCONNECTED"

        print()
        print("📡 GSM INFORMATION")
        print("   GSM Status    : DISCONNECTED")

        return

    print()
    print("📡 Updating GSM information...")

    # --------------------------------------------------------
    # SIM
    # --------------------------------------------------------

    cpin = send_at(
        "AT+CPIN?",
        timeout=3
    )

    if "READY" in cpin:

        latest_gsm["sim_status"] = "READY"

    else:

        latest_gsm["sim_status"] = "NOT READY"

    # --------------------------------------------------------
    # ICCID
    # --------------------------------------------------------

    iccid = send_at(
        "AT+QCCID",
        timeout=3
    )

    match = re.search(
        r"\+QCCID:\s*([0-9]+)",
        iccid
    )

    if match:

        latest_gsm["sim_iccid"] = (
            match.group(1)
        )

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

        latest_gsm["mobile_number"] = (
            match.group(1)
        )

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

        rssi = int(match.group(1))

        latest_gsm["signal_strength"] = rssi

        if rssi <= 31:

            latest_gsm["signal_dbm"] = (
                -113 + (2 * rssi)
            )

        else:

            latest_gsm["signal_dbm"] = None

    # --------------------------------------------------------
    # NETWORK REGISTRATION
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

        status = int(match.group(1))

        if status in (1, 5):

            latest_gsm["network_status"] = (
                "REGISTERED"
            )

        else:

            latest_gsm["network_status"] = (
                "NOT REGISTERED"
            )

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

        latest_gsm["operator"] = (
            match.group(1)
        )

    # --------------------------------------------------------
    # PING / LATENCY
    # --------------------------------------------------------

    ping_start = time.time()

    ping = send_at(
        'AT+QPING=1,"8.8.8.8",5,1',
        timeout=8
    )

    match = re.search(
        r"time[=:]\s*([0-9.]+)",
        ping,
        re.IGNORECASE
    )

    if match:

        latest_gsm["latency_ms"] = float(
            match.group(1)
        )

    elif "OK" in ping:

        latest_gsm["latency_ms"] = round(
            (time.time() - ping_start) * 1000,
            2
        )

    else:

        latest_gsm["latency_ms"] = None

    latest_gsm["gsm_status"] = "Connected"

    # --------------------------------------------------------
    # PRINT GSM
    # --------------------------------------------------------

    print()
    print("📡 GSM INFORMATION")
    print(
        f"   GSM Status    : "
        f"{latest_gsm['gsm_status']}"
    )
    print(
        f"   SIM Status    : "
        f"{latest_gsm['sim_status']}"
    )
    print(
        f"   ICCID         : "
        f"{latest_gsm['sim_iccid']}"
    )
    print(
        f"   Mobile Number : "
        f"{latest_gsm['mobile_number']}"
    )
    print(
        f"   Signal RSSI   : "
        f"{latest_gsm['signal_strength']}"
    )
    print(
        f"   Signal dBm    : "
        f"{latest_gsm['signal_dbm']}"
    )
    print(
        f"   Network       : "
        f"{latest_gsm['network_status']}"
    )
    print(
        f"   Operator      : "
        f"{latest_gsm['operator']}"
    )
    print(
        f"   Latency       : "
        f"{latest_gsm['latency_ms']} ms"
    )


# ============================================================
# GNSS
# ============================================================

def start_gnss():

    global gnss_enabled

    if not ensure_modem():

        return False

    response = send_at(
        "AT+QGPS=1",
        timeout=5
    )

    if "OK" in response:

        gnss_enabled = True

        print("🛰️ GNSS enabled")

        return True

    # Already enabled may return ERROR.
    # Check actual status.

    status = send_at(
        "AT+QGPS?",
        timeout=3
    )

    if "+QGPS: 1" in status:

        gnss_enabled = True

        print("🛰️✅ GNSS already enabled")

        return True

    gnss_enabled = False

    print("❌ Could not enable GNSS")

    return False


def ensure_gnss():

    global gnss_enabled

    if not ensure_modem():

        return False

    status = send_at(
        "AT+QGPS?",
        timeout=3
    )

    if "+QGPS: 1" in status:

        gnss_enabled = True

        return True

    print()
    print("⚠️ GNSS disabled")
    print("🔄 Restarting GNSS...")

    return start_gnss()


def get_satellite_count():

    """
    Try to obtain satellites from GGA NMEA.
    """

    response = send_at(
        'AT+QGPSGNMEA="GGA"',
        timeout=3
    )

    # Example:
    # $GNGGA,...,11,....

    for line in response.splitlines():

        if (
            "$GNGGA" in line
            or "$GPGGA" in line
        ):

            parts = line.strip().split(",")

            try:

                # GGA satellite field
                # Index 7
                if len(parts) > 7:

                    return int(parts[7])

            except Exception:
                pass

    return None


def get_gnss_location():

    global latest_gnss

    if not ensure_gnss():

        return False

    response = send_at(
        "AT+QGPSLOC=0",
        timeout=5
    )

    match = re.search(
        r"\+QGPSLOC:\s*([^\r\n]+)",
        response
    )

    if not match:

        latest_gnss["gnss_status"] = "NO FIX"

        return False

    values = [
        x.strip()
        for x in match.group(1).split(",")
    ]

    try:

        # Quectel QGPSLOC format:
        #
        # UTC,
        # latitude,
        # longitude,
        # HDOP,
        # altitude,
        # fix,
        # course,
        # speed,
        # date,
        # ...
        #
        # The exact trailing fields can vary.

        if len(values) < 5:

            latest_gnss["gnss_status"] = "NO FIX"

            return False

        gps_utc = values[0]

        latitude = float(values[1])
        longitude = float(values[2])
        altitude = float(values[4])

        # 0 usually means invalid/no fix.
        # Valid QGPSLOC normally contains coordinates.

        if (
            abs(latitude) < 0.000001
            and abs(longitude) < 0.000001
        ):

            latest_gnss["gnss_status"] = "NO FIX"

            return False

        satellites = get_satellite_count()

        latest_gnss = {

            "gnss_status": "FIX",

            "latitude": latitude,

            "longitude": longitude,

            "altitude_m": altitude,

            "satellites": satellites,

            "gps_utc": gps_utc,
        }

        return True

    except Exception:

        latest_gnss["gnss_status"] = "NO FIX"

        return False


def update_gnss():

    print()
    print("🛰️ Checking GNSS...")

    fixed = get_gnss_location()

    if not fixed:

        print("🛰️ GNSS: NO FIX")

        return

    print(
        "📍 GNSS FIX | "
        f"LAT={latest_gnss['latitude']} | "
        f"LON={latest_gnss['longitude']} | "
        f"ALT={latest_gnss['altitude_m']} m | "
        f"SAT={latest_gnss['satellites']}"
    )

    print(
        f"device_id={DEVICE_ID}, "
        f"BP_raw=0, "
        f"FP_raw=0, "
        f"CR_raw=0, "
        f"BC_raw=0, "
        f"GNSS=FIX, "
        f"LAT={latest_gnss['latitude']}, "
        f"LON={latest_gnss['longitude']}, "
        f"SAT={latest_gnss['satellites']}"
    )


# ============================================================
# PRESSURE LOGIC
# ============================================================

def process_pressure(
    bp,
    fp,
    cr,
    bc
):

    global first_pressure_stored
    global first_gnss_fix_stored
    global last_raw

    current_raw = (
        bp,
        fp,
        cr,
        bc
    )

    # --------------------------------------------------------
    # FIRST PRESSURE READING
    # --------------------------------------------------------

    if not first_pressure_stored:

        print()
        print("📌 FIRST PRESSURE READING")

        print(
            f"   BP = {bp}"
        )
        print(
            f"   FP = {fp}"
        )
        print(
            f"   CR = {cr}"
        )
        print(
            f"   BC = {bc}"
        )

        success = insert_database_record(
            bp,
            fp,
            cr,
            bc,
            record_type="PRESSURE"
        )

        if success:

            first_pressure_stored = True

            # IMPORTANT:
            # last_raw changes ONLY after successful
            # pressure insertion.

            last_raw = current_raw

        return

    # --------------------------------------------------------
    # FIRST GNSS FIX
    #
    # This is checked independently of pressure.
    # --------------------------------------------------------

    if (
        not first_gnss_fix_stored
        and latest_gnss["gnss_status"] == "FIX"
    ):

        print()
        print("🛰️✅ FIRST GNSS FIX RECEIVED")
        print("📥 One GNSS record will be stored in SQLite")

        print(
            f"📍 GNSS FIX | "
            f"LAT={latest_gnss['latitude']} | "
            f"LON={latest_gnss['longitude']} | "
            f"ALT={latest_gnss['altitude_m']} m | "
            f"SAT={latest_gnss['satellites']}"
        )

        print(
            f"device_id={DEVICE_ID}, "
            f"BP_raw={bp}, "
            f"FP_raw={fp}, "
            f"CR_raw={cr}, "
            f"BC_raw={bc}, "
            f"GNSS=FIX, "
            f"LAT={latest_gnss['latitude']}, "
            f"LON={latest_gnss['longitude']}, "
            f"SAT={latest_gnss['satellites']}"
        )

        success = insert_database_record(
            bp,
            fp,
            cr,
            bc,
            record_type="GNSS"
        )

        if success:

            # IMPORTANT:
            # GPS-only record does NOT modify last_raw.

            first_gnss_fix_stored = True

        return

    # --------------------------------------------------------
    # PRESSURE CHANGE CALCULATION
    # --------------------------------------------------------

    if last_raw is None:

        return

    bp_diff = abs(
        bp - last_raw[0]
    )

    fp_diff = abs(
        fp - last_raw[1]
    )

    cr_diff = abs(
        cr - last_raw[2]
    )

    bc_diff = abs(
        bc - last_raw[3]
    )

    # --------------------------------------------------------
    # ANY CHANNEL >= 326
    # --------------------------------------------------------

    if (
        bp_diff >= RAW_THRESHOLD
        or fp_diff >= RAW_THRESHOLD
        or cr_diff >= RAW_THRESHOLD
        or bc_diff >= RAW_THRESHOLD
    ):

        print()
        print("⚠️ PRESSURE CHANGE DETECTED")

        print(
            f"   BP diff = {bp_diff}"
        )
        print(
            f"   FP diff = {fp_diff}"
        )
        print(
            f"   CR diff = {cr_diff}"
        )
        print(
            f"   BC diff = {bc_diff}"
        )

        print()
        print("📊 CURRENT PRESSURE")

        print(f"   BP = {bp}")
        print(f"   FP = {fp}")
        print(f"   CR = {cr}")
        print(f"   BC = {bc}")

        success = insert_database_record(
            bp,
            fp,
            cr,
            bc,
            record_type="PRESSURE"
        )

        if success:

            # IMPORTANT:
            # Update last_raw ONLY after successful DB insert.

            last_raw = current_raw

    else:

        # ----------------------------------------------------
        # NO SIGNIFICANT PRESSURE CHANGE
        # ----------------------------------------------------

        print(
            f"\r⏭ No significant pressure change "
            f"→ Skipped DB insert "
            f"(BP={bp}, FP={fp}, CR={cr}, BC={bc})",
            end="",
            flush=True
        )


# ============================================================
# MAIN
# ============================================================

def main():

    global last_gsm_update
    global last_gnss_update

    initialize_database()

    if not initialize_ads():

        return

    print()
    print("🔌 Initializing EC200U...")

    if not open_gsm():

        print()
        print(
            "⚠️ EC200U unavailable."
        )
        print(
            "Pressure logging will continue."
        )

    else:

        print(
            "🛰️ Starting / checking GNSS..."
        )

        start_gnss()

    print()
    print("=" * 75)
    print("🚀 Capture system started")
    print("=" * 75)

    print(
        f"📊 RAW_THRESHOLD = {RAW_THRESHOLD}"
    )

    print(
        f"⏱ READ_INTERVAL = {READ_INTERVAL} sec"
    )

    print(
        f"📡 GSM interval = {GSM_INTERVAL} sec"
    )

    print(
        f"🛰️ GNSS interval = {GNSS_INTERVAL} sec"
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
        "4. Any pressure difference >= 326 → STORE ALL 4 readings"
    )

    print(
        "5. Pressure difference < 326 → SKIP"
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

    # --------------------------------------------------------
    # Timers
    # --------------------------------------------------------

    last_gsm_update = 0
    last_gnss_update = 0

    try:

        while True:

            now = time.time()

            # ------------------------------------------------
            # GSM
            # ------------------------------------------------

            if (
                now - last_gsm_update
                >= GSM_INTERVAL
            ):

                update_gsm_information()

                last_gsm_update = now

            # ------------------------------------------------
            # GNSS
            # ------------------------------------------------

            if (
                now - last_gnss_update
                >= GNSS_INTERVAL
            ):

                update_gnss()

                last_gnss_update = now

            # ------------------------------------------------
            # PRESSURE
            # ------------------------------------------------

            pressure = read_pressure()

            if pressure is not None:

                process_pressure(
                    pressure[0],
                    pressure[1],
                    pressure[2],
                    pressure[3]
                )

            time.sleep(
                READ_INTERVAL
            )

    except KeyboardInterrupt:

        print()
        print()
        print("🛑 Capture system stopped by user")

    finally:

        close_gsm()


# ============================================================
# PROGRAM ENTRY
# ============================================================

if __name__ == "__main__":

    main()