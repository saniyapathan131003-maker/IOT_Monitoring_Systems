#!/usr/bin/env python3

import os
import sys
import time
import sqlite3
import threading
import re
from datetime import datetime


# ============================================================
# CONFIGURATION
# ============================================================

RAW_THRESHOLD = 326

# Pressure reading interval
PRESSURE_READ_INTERVAL = 0.1

# Communication intervals
GNSS_INTERVAL = 5.0
GSM_INTERVAL = 30.0
MODEM_CHECK_INTERVAL = 5.0

# EC200U
SERIAL_PORT = "/dev/ttyAMA3"
BAUD_RATE = 115200

# Database
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.path.join(BASE_DIR, "db")
DB_PATH = os.path.join(DB_DIR, "new_db.db")

os.makedirs(DB_DIR, exist_ok=True)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


# ============================================================
# GLOBAL LOCKS / EVENTS
# ============================================================

state_lock = threading.Lock()
serial_lock = threading.Lock()
stop_event = threading.Event()


# ============================================================
# MODEM GLOBAL VARIABLES
# ============================================================

modem_serial = None
modem_connected = False


# ============================================================
# GSM STATUS
# ============================================================

gsm_info = {
    "gsm_status": "Disconnected",
    "sim_status": "UNKNOWN",
    "sim_iccid": None,
    "mobile_number": None,
    "signal_strength": None,
    "signal_dbm": None,
    "network_status": "UNKNOWN",
    "operator": None,
    "latency_ms": None,
}


# ============================================================
# GNSS STATUS
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
# DATABASE COLUMNS
# ============================================================

REQUIRED_COLUMNS = {
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


# ============================================================
# DATABASE CONNECTION
# ============================================================

def get_db_connection():

    conn = sqlite3.connect(
        DB_PATH,
        timeout=30,
        check_same_thread=False
    )

    conn.row_factory = sqlite3.Row

    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except Exception:
        pass

    conn.execute("PRAGMA busy_timeout=30000")

    return conn


# ============================================================
# DATABASE INITIALIZATION
# ============================================================

def initialize_database():

    conn = get_db_connection()

    try:

        conn.execute("""
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

        rows = conn.execute(
            "PRAGMA table_info(brake_pressure_log)"
        ).fetchall()

        existing_columns = {
            row["name"] for row in rows
        }

        for column, datatype in REQUIRED_COLUMNS.items():

            if column not in existing_columns:

                conn.execute(
                    f"ALTER TABLE brake_pressure_log "
                    f"ADD COLUMN {column} {datatype}"
                )

                print(
                    f"✅ Added database column: {column}",
                    flush=True
                )

        conn.commit()

    except Exception as e:

        print(
            f"❌ Database initialization error: {e}",
            flush=True
        )

        raise

    finally:

        conn.close()


# ============================================================
# DEVICE ID
# ============================================================

def get_device_id():

    conn = get_db_connection()

    try:

        table = conn.execute("""
            SELECT name
            FROM sqlite_master
            WHERE type='table'
            AND name='device_config'
        """).fetchone()

        if table is None:
            return "UNKNOWN"

        row = conn.execute(
            "SELECT device_id FROM device_config LIMIT 1"
        ).fetchone()

        if row and row["device_id"]:

            return str(row["device_id"])

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
# DATABASE INSERT
# ============================================================

def insert_database_record(
    device_id,
    pressure_values,
    timestamp,
    record_reason
):

    with state_lock:

        gsm = dict(gsm_info)
        gnss = dict(gnss_info)

    try:

        bp_raw = int(pressure_values[0])
        fp_raw = int(pressure_values[1])
        cr_raw = int(pressure_values[2])
        bc_raw = int(pressure_values[3])

    except Exception as e:

        print(
            f"❌ Invalid pressure values: {e}",
            flush=True
        )

        return False

    conn = None

    try:

        conn = get_db_connection()

        cursor = conn.execute("""
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
                ?, ?, ?, ?, ?, ?, 0,

                ?, ?, ?, ?, ?, ?, ?, ?, ?,

                ?, ?, ?, ?, ?, ?
            )
        """, (
            device_id,

            bp_raw,
            fp_raw,
            cr_raw,
            bc_raw,

            timestamp,

            gsm["gsm_status"],
            gsm["sim_status"],
            gsm["sim_iccid"],
            gsm["mobile_number"],
            gsm["signal_strength"],
            gsm["signal_dbm"],
            gsm["network_status"],
            gsm["operator"],
            gsm["latency_ms"],

            gnss["gnss_status"],
            gnss["latitude"],
            gnss["longitude"],
            gnss["altitude_m"],
            gnss["satellites"],
            gnss["gps_utc"],
        ))

        conn.commit()

        db_id = cursor.lastrowid

        # ONLY PRINT WHEN DB INSERT ACTUALLY HAPPENS
        print(
            f"💾 DB INSERTED | "
            f"ID={db_id} | "
            f"Reason={record_reason} | "
            f"BP={bp_raw} | "
            f"FP={fp_raw} | "
            f"CR={cr_raw} | "
            f"BC={bc_raw} | "
            f"Uploaded=0",
            flush=True
        )

        return True

    except Exception as e:

        print(
            f"❌ SQLite INSERT ERROR: {e}",
            flush=True
        )

        return False

    finally:

        if conn is not None:

            conn.close()


# ============================================================
# ADS1115
# ============================================================

ADS_AVAILABLE = False

bp_channel = None
fp_channel = None
cr_channel = None
bc_channel = None

# Last valid pressure reading
last_valid_pressure = (0, 0, 0, 0)


def initialize_ads1115():

    global ADS_AVAILABLE
    global bp_channel
    global fp_channel
    global cr_channel
    global bc_channel

    try:

        import board
        import busio
        import adafruit_ads1x15.ads1115 as ADS
        from adafruit_ads1x15.analog_in import AnalogIn

        print(
            "🔌 Checking ADS1115 I2C...",
            flush=True
        )

        i2c = busio.I2C(
            board.SCL,
            board.SDA
        )

        ads = ADS.ADS1115(i2c)

        ads.gain = 1

        # IMPORTANT:
        # Numeric channel numbers are used.
        #
        # A0 -> 0
        # A1 -> 1
        # A2 -> 2
        # A3 -> 3

        bp_channel = AnalogIn(ads, 0)
        fp_channel = AnalogIn(ads, 1)
        cr_channel = AnalogIn(ads, 2)
        bc_channel = AnalogIn(ads, 3)

        ADS_AVAILABLE = True

        print(
            "✅ ADS1115 sensor detected and initialized.",
            flush=True
        )

        # Test reading
        test_values = (
            bp_channel.value,
            fp_channel.value,
            cr_channel.value,
            bc_channel.value
        )

        print(
            f"📊 ADS1115 initial raw values: "
            f"BP={test_values[0]}, "
            f"FP={test_values[1]}, "
            f"CR={test_values[2]}, "
            f"BC={test_values[3]}",
            flush=True
        )

        return True

    except Exception as e:

        ADS_AVAILABLE = False

        print(
            f"❌ ADS1115 initialization failed: {e}",
            flush=True
        )

        return False


def read_pressure_values():

    global last_valid_pressure

    if not ADS_AVAILABLE:

        return last_valid_pressure

    try:

        bp = int(bp_channel.value)
        fp = int(fp_channel.value)
        cr = int(cr_channel.value)
        bc = int(bc_channel.value)

        current = (
            bp,
            fp,
            cr,
            bc
        )

        last_valid_pressure = current

        return current

    except Exception as e:

        # DO NOT RETURN ZERO.
        # Keep the previous valid reading.

        print(
            f"⚠️ ADS1115 temporary read error: {e}",
            flush=True
        )

        return last_valid_pressure


# ============================================================
# MODEM CLOSE
# ============================================================

def close_modem():

    global modem_serial
    global modem_connected

    with serial_lock:

        try:

            if modem_serial is not None:

                modem_serial.close()

        except Exception:

            pass

        modem_serial = None
        modem_connected = False

    with state_lock:

        gsm_info["gsm_status"] = "Disconnected"


# ============================================================
# MODEM OPEN
# ============================================================

def open_modem():

    global modem_serial
    global modem_connected

    try:

        import serial

        with serial_lock:

            if modem_serial is not None:

                try:

                    if modem_serial.is_open:
                        modem_serial.close()

                except Exception:

                    pass

            modem_serial = serial.Serial(
                port=SERIAL_PORT,
                baudrate=BAUD_RATE,
                timeout=1,
                write_timeout=2
            )

            time.sleep(1)

            modem_connected = True

        with state_lock:

            gsm_info["gsm_status"] = "Connected"

        print(
            f"✅ EC200U connected on {SERIAL_PORT}",
            flush=True
        )

        return True

    except Exception as e:

        modem_connected = False

        with state_lock:

            gsm_info["gsm_status"] = "Disconnected"

        print(
            f"⚠️ EC200U connection failed: {e}",
            flush=True
        )

        return False


# ============================================================
# SEND AT COMMAND
# ============================================================

def send_at(command, timeout=3):

    global modem_serial
    global modem_connected

    with serial_lock:

        if modem_serial is None:

            return ""

        try:

            if not modem_serial.is_open:

                modem_connected = False

                return ""

            modem_serial.reset_input_buffer()

            modem_serial.write(
                (command + "\r").encode()
            )

            modem_serial.flush()

            end_time = (
                time.monotonic()
                + timeout
            )

            response = bytearray()

            while time.monotonic() < end_time:

                waiting = modem_serial.in_waiting

                if waiting:

                    response.extend(
                        modem_serial.read(waiting)
                    )

                    text = response.decode(
                        errors="ignore"
                    )

                    if "\nOK" in text:
                        break

                    if "\nERROR" in text:
                        break

                time.sleep(0.05)

            return response.decode(
                errors="ignore"
            ).strip()

        except Exception:

            modem_connected = False

            with state_lock:

                gsm_info["gsm_status"] = "Disconnected"

            return ""


# ============================================================
# MODEM HEALTH CHECK
# ============================================================

def modem_is_alive():

    global modem_connected

    response = send_at(
        "AT",
        timeout=2
    )

    if "OK" in response:

        modem_connected = True

        with state_lock:

            gsm_info["gsm_status"] = "Connected"

        return True

    modem_connected = False

    with state_lock:

        gsm_info["gsm_status"] = "Disconnected"

    return False


# ============================================================
# PARSE CSQ
# ============================================================

def parse_csq(response):

    if not response:

        return None, None

    match = re.search(
        r"\+CSQ:\s*(\d+)\s*,\s*(\d+)",
        response
    )

    if not match:

        return None, None

    try:

        rssi = int(match.group(1))

        if rssi == 99:

            return None, None

        dbm = -113 + (2 * rssi)

        return rssi, dbm

    except Exception:

        return None, None


# ============================================================
# PARSE NETWORK REGISTRATION
# ============================================================

def parse_registration(response):

    if not response:

        return "UNKNOWN"

    match = re.search(
        r"\+CREG:\s*(?:\d+\s*,\s*)?(\d+)",
        response
    )

    if not match:

        return "UNKNOWN"

    value = match.group(1)

    if value in ("1", "5"):

        return "REGISTERED"

    if value == "2":

        return "SEARCHING"

    if value == "3":

        return "REGISTRATION DENIED"

    if value == "0":

        return "NOT REGISTERED"

    return "UNKNOWN"


# ============================================================
# PARSE OPERATOR
# ============================================================

def parse_operator(response):

    if not response:

        return None

    match = re.search(
        r'\+COPS:\s*\d+\s*,\s*\d+\s*,\s*"([^"]+)"',
        response
    )

    if match:

        return match.group(1)

    return None


# ============================================================
# PARSE QPING
# ============================================================

def parse_qping(response):

    if not response:

        return None

    # Typical:
    #
    # +QPING: 0,"8.8.8.8",64,8,255
    #
    #                 ^
    #                 latency

    match = re.search(
        r'\+QPING:\s*\d+\s*,\s*"[^"]+"\s*,\s*\d+\s*,\s*([\d.]+)',
        response
    )

    if match:

        try:

            return float(
                match.group(1)
            )

        except Exception:

            pass

    # Fallback parser
    match = re.search(
        r'\+QPING:.*?,.*?,.*?,\s*([\d.]+)\s*,',
        response
    )

    if match:

        try:

            return float(
                match.group(1)
            )

        except Exception:

            pass

    return None


# ============================================================
# UPDATE GSM INFORMATION
# ============================================================

def update_gsm_information():

    if not modem_is_alive():

        return False

    # --------------------------------------------------------
    # SIM
    # --------------------------------------------------------

    sim_response = send_at(
        "AT+CPIN?",
        timeout=2
    )

    sim_status = "UNKNOWN"

    if "READY" in sim_response:

        sim_status = "READY"

    elif "SIM PIN" in sim_response:

        sim_status = "SIM PIN"

    # --------------------------------------------------------
    # ICCID
    # --------------------------------------------------------

    iccid_response = send_at(
        "AT+QCCID",
        timeout=2
    )

    sim_iccid = None

    match = re.search(
        r"\+QCCID:\s*([0-9A-Za-z]+)",
        iccid_response
    )

    if match:

        sim_iccid = match.group(1)

    # --------------------------------------------------------
    # MOBILE NUMBER
    # --------------------------------------------------------

    cnum_response = send_at(
        "AT+CNUM",
        timeout=2
    )

    mobile_number = None

    match = re.search(
        r'\+CNUM:\s*"[^"]*"\s*,\s*"([^"]+)"',
        cnum_response
    )

    if match:

        mobile_number = match.group(1)

    # --------------------------------------------------------
    # SIGNAL
    # --------------------------------------------------------

    csq_response = send_at(
        "AT+CSQ",
        timeout=2
    )

    rssi, dbm = parse_csq(
        csq_response
    )

    # --------------------------------------------------------
    # NETWORK
    # --------------------------------------------------------

    creg_response = send_at(
        "AT+CREG?",
        timeout=2
    )

    network_status = parse_registration(
        creg_response
    )

    # --------------------------------------------------------
    # OPERATOR
    # --------------------------------------------------------

    cops_response = send_at(
        "AT+COPS?",
        timeout=5
    )

    operator = parse_operator(
        cops_response
    )

    # --------------------------------------------------------
    # LATENCY
    # --------------------------------------------------------

    ping_response = send_at(
        'AT+QPING=1,"8.8.8.8",5,1',
        timeout=8
    )

    latency = parse_qping(
        ping_response
    )

    # --------------------------------------------------------
    # UPDATE GLOBAL GSM DATA
    # --------------------------------------------------------

    with state_lock:

        gsm_info["gsm_status"] = (
            "Connected"
            if modem_connected
            else "Disconnected"
        )

        gsm_info["sim_status"] = sim_status

        gsm_info["sim_iccid"] = sim_iccid

        gsm_info["mobile_number"] = mobile_number

        gsm_info["signal_strength"] = rssi

        gsm_info["signal_dbm"] = dbm

        gsm_info["network_status"] = network_status

        gsm_info["operator"] = operator

        gsm_info["latency_ms"] = latency

    return True


# ============================================================
# ENABLE GNSS
# ============================================================

def ensure_gnss():

    if not modem_is_alive():

        return False

    response = send_at(
        "AT+QGPS?",
        timeout=2
    )

    if "+QGPS: 1" not in response:

        response = send_at(
            "AT+QGPS=1",
            timeout=5
        )

        time.sleep(1)

    return True


# ============================================================
# NMEA COORDINATE CONVERSION
# ============================================================

def convert_nmea_coordinate(
    value,
    direction
):

    try:

        if not value:

            return None

        value = float(value)

        degrees = int(
            value / 100
        )

        minutes = (
            value
            - degrees * 100
        )

        decimal = (
            degrees
            + minutes / 60.0
        )

        if direction in ("S", "W"):

            decimal = -decimal

        return decimal

    except Exception:

        return None


# ============================================================
# PARSE GGA
# ============================================================

def parse_gga(response):

    if not response:

        return None

    for line in response.splitlines():

        line = line.strip()

        if (
            "$GPGGA" not in line
            and "$GNGGA" not in line
        ):

            continue

        parts = line.split(",")

        if len(parts) < 10:

            continue

        try:

            utc = parts[1]

            lat_raw = parts[2]
            lat_dir = parts[3]

            lon_raw = parts[4]
            lon_dir = parts[5]

            fix_quality = int(
                parts[6] or 0
            )

            satellites = None

            if parts[7]:

                satellites = int(
                    parts[7]
                )

            altitude = None

            if parts[9]:

                altitude = float(
                    parts[9]
                )

            latitude = convert_nmea_coordinate(
                lat_raw,
                lat_dir
            )

            longitude = convert_nmea_coordinate(
                lon_raw,
                lon_dir
            )

            if fix_quality > 0:

                return {
                    "gnss_status": "FIX",
                    "latitude": latitude,
                    "longitude": longitude,
                    "altitude_m": altitude,
                    "satellites": satellites,
                    "gps_utc": utc
                }

            return {
                "gnss_status": "NO FIX",
                "latitude": None,
                "longitude": None,
                "altitude_m": None,
                "satellites": satellites,
                "gps_utc": utc
            }

        except Exception:

            continue

    return None


# ============================================================
# PARSE QGPSLOC
# ============================================================

def parse_qgpsloc(response):

    if not response:

        return None

    match = re.search(
        r"\+QGPSLOC:\s*([^\r\n]+)",
        response
    )

    if not match:

        return None

    try:

        values = [
            x.strip()
            for x in match.group(1).split(",")
        ]

        if len(values) < 5:

            return None

        utc = values[0]

        latitude = float(
            values[1]
        )

        longitude = float(
            values[2]
        )

        altitude = float(
            values[4]
        )

        return {
            "gnss_status": "FIX",
            "latitude": latitude,
            "longitude": longitude,
            "altitude_m": altitude,
            "satellites": None,
            "gps_utc": utc
        }

    except Exception:

        return None


# ============================================================
# READ GNSS
# ============================================================

def read_gnss():

    if not modem_is_alive():

        with state_lock:

            gnss_info["gnss_status"] = "NO FIX"

        return False

    ensure_gnss()

    # --------------------------------------------------------
    # QGPSLOC
    # --------------------------------------------------------

    loc_response = send_at(
        "AT+QGPSLOC=0",
        timeout=4
    )

    qgpsloc_data = parse_qgpsloc(
        loc_response
    )

    # --------------------------------------------------------
    # GGA
    # --------------------------------------------------------

    gga_response = send_at(
        'AT+QGPSGNMEA="GGA"',
        timeout=3
    )

    gga_data = parse_gga(
        gga_response
    )

    # --------------------------------------------------------
    # COMBINE
    # --------------------------------------------------------

    parsed = None

    if qgpsloc_data:

        parsed = dict(
            qgpsloc_data
        )

    if gga_data:

        if parsed is None:

            parsed = dict(
                gga_data
            )

        else:

            if gga_data["gnss_status"] == "FIX":

                parsed["gnss_status"] = "FIX"

                if (
                    gga_data["latitude"]
                    is not None
                ):

                    parsed["latitude"] = (
                        gga_data["latitude"]
                    )

                if (
                    gga_data["longitude"]
                    is not None
                ):

                    parsed["longitude"] = (
                        gga_data["longitude"]
                    )

                if (
                    gga_data["altitude_m"]
                    is not None
                ):

                    parsed["altitude_m"] = (
                        gga_data["altitude_m"]
                    )

            else:

                if not qgpsloc_data:

                    parsed["gnss_status"] = "NO FIX"

            parsed["satellites"] = (
                gga_data["satellites"]
            )

            parsed["gps_utc"] = (
                gga_data["gps_utc"]
            )

    # --------------------------------------------------------
    # UPDATE GNSS
    # --------------------------------------------------------

    if parsed:

        with state_lock:

            gnss_info.update(parsed)

        if parsed["gnss_status"] == "FIX":

            print(
                f"📍 GNSS FIX | "
                f"LAT={parsed['latitude']:.8f} | "
                f"LON={parsed['longitude']:.8f} | "
                f"ALT={parsed['altitude_m']} m | "
                f"SAT={parsed['satellites']}",
                flush=True
            )

            return True

    # No valid fix
    with state_lock:

        gnss_info["gnss_status"] = "NO FIX"

        gnss_info["latitude"] = None

        gnss_info["longitude"] = None

        gnss_info["altitude_m"] = None

        if parsed:

            gnss_info["satellites"] = (
                parsed.get("satellites")
            )

            gnss_info["gps_utc"] = (
                parsed.get("gps_utc")
            )

    print(
        "📍 GNSS NO FIX | "
        "LAT=None | "
        "LON=None | "
        f"SAT={gnss_info['satellites']}",
        flush=True
    )

    return False


# ============================================================
# STARTUP GSM INFORMATION
# ============================================================

def print_startup_gsm_information():

    print(
        "\n============================================================",
        flush=True
    )

    print(
        "📡 EC200U GSM INFORMATION",
        flush=True
    )

    print(
        "============================================================",
        flush=True
    )

    if not modem_connected:

        print(
            "GSM Status   : Disconnected",
            flush=True
        )

        print(
            "============================================================",
            flush=True
        )

        return

    ati = send_at(
        "ATI",
        timeout=3
    )

    print(
        f"ATI Response : {ati}",
        flush=True
    )

    imei = send_at(
        "AT+CGSN",
        timeout=3
    )

    print(
        f"IMEI         : {imei}",
        flush=True
    )

    update_gsm_information()

    with state_lock:

        gsm = dict(gsm_info)

    print(
        f"GSM Status   : {gsm['gsm_status']}",
        flush=True
    )

    print(
        f"SIM Status   : {gsm['sim_status']}",
        flush=True
    )

    print(
        f"ICCID        : {gsm['sim_iccid']}",
        flush=True
    )

    print(
        f"Mobile No.   : {gsm['mobile_number']}",
        flush=True
    )

    print(
        f"RSSI         : {gsm['signal_strength']}",
        flush=True
    )

    print(
        f"dBm          : {gsm['signal_dbm']}",
        flush=True
    )

    print(
        f"Network      : {gsm['network_status']}",
        flush=True
    )

    print(
        f"Operator     : {gsm['operator']}",
        flush=True
    )

    print(
        f"Latency      : {gsm['latency_ms']} ms",
        flush=True
    )

    print(
        "============================================================\n",
        flush=True
    )


# ============================================================
# COMMUNICATION THREAD
# ============================================================

def communication_worker():

    global modem_connected

    last_gnss_time = 0

    last_gsm_time = 0

    last_modem_check = 0

    first_connection_attempt = True

    startup_information_printed = False

    while not stop_event.is_set():

        now = time.monotonic()

        # ====================================================
        # MODEM CONNECTION
        # ====================================================

        if not modem_connected:

            if (
                first_connection_attempt
                or (
                    now - last_modem_check
                    >= MODEM_CHECK_INTERVAL
                )
            ):

                first_connection_attempt = False

                last_modem_check = now

                print(
                    "📡 Checking EC200U...",
                    flush=True
                )

                if open_modem():

                    if modem_is_alive():

                        print(
                            "✅ EC200U responding to AT.",
                            flush=True
                        )

                        ensure_gnss()

                        if not startup_information_printed:

                            print_startup_gsm_information()

                            startup_information_printed = True

                        # First GNSS check immediately
                        read_gnss()

                        last_gnss_time = (
                            time.monotonic()
                        )

                        last_gsm_time = (
                            time.monotonic()
                        )

                time.sleep(0.2)

                continue

        # ====================================================
        # MODEM HEALTH
        # ====================================================

        if (
            now - last_modem_check
            >= MODEM_CHECK_INTERVAL
        ):

            last_modem_check = now

            if not modem_is_alive():

                print(
                    "⚠️ EC200U disconnected. "
                    "Reconnecting...",
                    flush=True
                )

                close_modem()

                continue

        # ====================================================
        # GNSS EVERY 5 SECONDS
        # ====================================================

        if (
            modem_connected
            and (
                now - last_gnss_time
                >= GNSS_INTERVAL
            )
        ):

            last_gnss_time = now

            try:

                read_gnss()

            except Exception as e:

                print(
                    f"⚠️ GNSS error: {e}",
                    flush=True
                )

        # ====================================================
        # GSM EVERY 30 SECONDS
        # ====================================================

        if (
            modem_connected
            and (
                now - last_gsm_time
                >= GSM_INTERVAL
            )
        ):

            last_gsm_time = now

            try:

                update_gsm_information()

            except Exception as e:

                print(
                    f"⚠️ GSM update error: {e}",
                    flush=True
                )

        time.sleep(0.1)


# ============================================================
# LIVE STATUS
# ============================================================

def print_status(
    device_id,
    pressure_values
):

    with state_lock:

        gsm = dict(gsm_info)

        gnss = dict(gnss_info)

    timestamp = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    print(
        f"device_id={device_id}, "
        f"BP_raw={pressure_values[0]}, "
        f"FP_raw={pressure_values[1]}, "
        f"CR_raw={pressure_values[2]}, "
        f"BC_raw={pressure_values[3]}, "
        f"GNSS={gnss['gnss_status']}, "
        f"LAT={gnss['latitude']}, "
        f"LON={gnss['longitude']}, "
        f"SAT={gnss['satellites']}, "
        f"GSM={gsm['gsm_status']}, "
        f"RSSI={gsm['signal_strength']}, "
        f"dBm={gsm['signal_dbm']}, "
        f"Network={gsm['network_status']}, "
        f"Latency={gsm['latency_ms']} ms, "
        f"Timestamp={timestamp}",
        flush=True
    )


# ============================================================
# MAIN
# ============================================================

def main():

    global modem_connected

    print(
        "\n============================================================",
        flush=True
    )

    print(
        "🚀 PRESSURE + GSM + GNSS CAPTURE SYSTEM",
        flush=True
    )

    print(
        "============================================================",
        flush=True
    )

    # ========================================================
    # DATABASE
    # ========================================================

    print(
        "🗄️ Initializing SQLite database...",
        flush=True
    )

    initialize_database()

    print(
        f"✅ Database: {DB_PATH}",
        flush=True
    )

    # ========================================================
    # DEVICE ID
    # ========================================================

    device_id = get_device_id()

    print(
        f"✅ Device ID = {device_id}",
        flush=True
    )

    # ========================================================
    # ADS1115
    # ========================================================

    initialize_ads1115()

    # ========================================================
    # START COMMUNICATION THREAD
    # ========================================================

    communication_thread = threading.Thread(
        target=communication_worker,
        daemon=True
    )

    communication_thread.start()

    print(
        "\n🚀 Pressure monitoring started...\n",
        flush=True
    )

    # ========================================================
    # PRESSURE DATABASE STATE
    # ========================================================

    last_raw = None

    first_pressure_stored = False

    first_gnss_fix_stored = False

    last_print_time = time.monotonic()

    # ========================================================
    # MAIN PRESSURE LOOP
    # ========================================================

    try:

        while True:

            loop_start = time.monotonic()

            # ------------------------------------------------
            # READ CURRENT PRESSURE
            # ------------------------------------------------

            current_raw = read_pressure_values()

            # ------------------------------------------------
            # FIRST PRESSURE RECORD
            # ------------------------------------------------

            if not first_pressure_stored:

                timestamp = datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                )

                success = insert_database_record(
                    device_id,
                    current_raw,
                    timestamp,
                    "FIRST_PRESSURE"
                )

                if success:

                    first_pressure_stored = True

                    last_raw = current_raw

                    print(
                        f"✅ FIRST PRESSURE STORED | "
                        f"last_raw={last_raw}",
                        flush=True
                    )

            # ------------------------------------------------
            # FIRST GNSS FIX RECORD
            #
            # This is exactly ONE additional record.
            #
            # IMPORTANT:
            # It does NOT change last_raw.
            # ------------------------------------------------

            with state_lock:

                current_gnss_status = (
                    gnss_info["gnss_status"]
                )

            if (
                first_pressure_stored
                and not first_gnss_fix_stored
                and current_gnss_status == "FIX"
            ):

                timestamp = datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                )

                success = insert_database_record(
                    device_id,
                    current_raw,
                    timestamp,
                    "FIRST_GNSS_FIX"
                )

                if success:

                    first_gnss_fix_stored = True

                    # DO NOT CHANGE last_raw HERE

                    print(
                        "📍 FIRST GNSS FIX STORED | "
                        "last_raw unchanged",
                        flush=True
                    )

            # ------------------------------------------------
            # PRESSURE THRESHOLD LOGIC
            # ------------------------------------------------

            if (
                first_pressure_stored
                and last_raw is not None
            ):

                differences = [
                    abs(
                        current_raw[i]
                        - last_raw[i]
                    )
                    for i in range(4)
                ]

                pressure_changed = any(
                    diff >= RAW_THRESHOLD
                    for diff in differences
                )

                # ------------------------------------------------
                # ONLY WHEN THRESHOLD IS REACHED
                # ------------------------------------------------

                if pressure_changed:

                    timestamp = datetime.now().strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )

                    success = insert_database_record(
                        device_id,
                        current_raw,
                        timestamp,
                        "PRESSURE_CHANGE"
                    )

                    if success:

                        # Update reference ONLY after DB insert
                        last_raw = current_raw

                        print(
                            f"📈 PRESSURE CHANGE DETECTED | "
                            f"BP_diff={differences[0]} | "
                            f"FP_diff={differences[1]} | "
                            f"CR_diff={differences[2]} | "
                            f"BC_diff={differences[3]} | "
                            f"Threshold={RAW_THRESHOLD}",
                            flush=True
                        )

                # ------------------------------------------------
                # IMPORTANT:
                #
                # If threshold is NOT reached:
                #
                # DO NOTHING.
                #
                # NO "SKIP" MESSAGE.
                # ------------------------------------------------

            # ------------------------------------------------
            # LIVE STATUS EVERY 1 SECOND
            # ------------------------------------------------

            now = time.monotonic()

            if (
                now - last_print_time
                >= 1.0
            ):

                last_print_time = now

                print_status(
                    device_id,
                    current_raw
                )

            # ------------------------------------------------
            # PRESSURE LOOP TIMING
            # ------------------------------------------------

            elapsed = (
                time.monotonic()
                - loop_start
            )

            remaining = (
                PRESSURE_READ_INTERVAL
                - elapsed
            )

            if remaining > 0:

                time.sleep(remaining)

    except KeyboardInterrupt:

        print(
            "\n🛑 Stopping capture system...",
            flush=True
        )

    except Exception as e:

        print(
            f"\n❌ MAIN LOOP ERROR: {e}",
            flush=True
        )

    finally:

        stop_event.set()

        close_modem()

        print(
            "✅ System stopped.",
            flush=True
        )


# ============================================================
# PROGRAM START
# ============================================================

if __name__ == "__main__":

    main()