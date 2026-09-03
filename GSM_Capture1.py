from pathlib import Path

code = r'''#!/usr/bin/env python3
import os
import re
import sys
import time
import sqlite3
import threading
from datetime import datetime

import serial

sys.stdout.reconfigure(encoding="utf-8")

# ============================================================
# CONFIG
# ============================================================
RAW_THRESHOLD = 326
READ_INTERVAL = 0.1

GSM_UPDATE_INTERVAL = 30.0
GNSS_UPDATE_INTERVAL = 5.0
MODEM_CHECK_INTERVAL = 5.0
MODEM_RECONNECT_INTERVAL = 5.0

SERIAL_PORT = "/dev/ttyAMA3"
BAUD_RATE = 115200
SERIAL_TIMEOUT = 2.0

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.path.join(BASE_DIR, "db")
DB_PATH = os.path.join(DB_DIR, "new_db.db")
os.makedirs(DB_DIR, exist_ok=True)

# ============================================================
# GLOBAL STATE
# ============================================================
serial_lock = threading.Lock()
ser = None
modem_connected = False
gnss_enabled = False

# FIX for previous NameError
first_pressure_stored = False
first_gnss_fix_stored = False
last_raw = None

last_modem_check = 0.0
last_modem_reconnect = 0.0
last_gsm_update = 0.0
last_gnss_update = 0.0
last_status_print = 0.0

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

gnss_info = {
    "gnss_status": "NO FIX",
    "latitude": None,
    "longitude": None,
    "altitude_m": None,
    "satellites": None,
    "gps_utc": None,
}

# ============================================================
# DATABASE
# ============================================================
def db_connect():
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=30000")
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except sqlite3.Error:
        pass
    return conn


def initialize_database():
    conn = db_connect()
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

        existing = {
            row["name"]
            for row in conn.execute(
                "PRAGMA table_info(brake_pressure_log)"
            ).fetchall()
        }

        required = {
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

        for name, datatype in required.items():
            if name not in existing:
                conn.execute(
                    f"ALTER TABLE brake_pressure_log ADD COLUMN {name} {datatype}"
                )

        conn.commit()
    finally:
        conn.close()


def get_device_id():
    conn = db_connect()
    try:
        try:
            row = conn.execute(
                "SELECT device_id FROM device_config LIMIT 1"
            ).fetchone()
            if row and row["device_id"]:
                return str(row["device_id"])
        except sqlite3.Error:
            pass
        return "UNKNOWN"
    finally:
        conn.close()


# ============================================================
# DATABASE INSERT
# ============================================================
def insert_record(current_raw, timestamp, record_type):
    conn = db_connect()

    try:
        values = (
            DEVICE_ID,
            int(current_raw[0]),
            int(current_raw[1]),
            int(current_raw[2]),
            int(current_raw[3]),
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
            gnss_info["gps_utc"],
        )

        cur = conn.execute("""
        INSERT INTO brake_pressure_log (
            device_id, BP_raw, FP_raw, CR_raw, BC_raw,
            timestamp, uploaded,
            gsm_status, sim_status, sim_iccid, mobile_number,
            signal_strength, signal_dbm, network_status, operator,
            latency_ms,
            gnss_status, latitude, longitude, altitude_m,
            satellites, gps_utc
        )
        VALUES (
            ?,?,?,?,?,?,?, ?,?,?,?,?,?,?,?,?,
            ?,?,?,?,?,?
        )
        """, values)

        conn.commit()

        print("\n💾 DB RECORD STORED", flush=True)
        print(f"   Type        : {record_type}", flush=True)
        print(f"   DB ID       : {cur.lastrowid}", flush=True)
        print(f"   Uploaded    : 0", flush=True)
        print(f"   Device ID   : {DEVICE_ID}", flush=True)
        print(f"   BP_raw      : {current_raw[0]}", flush=True)
        print(f"   FP_raw      : {current_raw[1]}", flush=True)
        print(f"   CR_raw      : {current_raw[2]}", flush=True)
        print(f"   BC_raw      : {current_raw[3]}", flush=True)
        print(f"   GSM Status  : {gsm_info['gsm_status']}", flush=True)
        print(f"   RSSI        : {gsm_info['signal_strength']}", flush=True)
        print(f"   Signal dBm  : {gsm_info['signal_dbm']}", flush=True)
        print(f"   Network     : {gsm_info['network_status']}", flush=True)
        print(f"   Latency     : {gsm_info['latency_ms']} ms", flush=True)
        print(f"   GNSS        : {gnss_info['gnss_status']}", flush=True)
        print(f"   LAT         : {gnss_info['latitude']}", flush=True)
        print(f"   LON         : {gnss_info['longitude']}", flush=True)
        print(f"   ALT         : {gnss_info['altitude_m']} m", flush=True)
        print(f"   SAT         : {gnss_info['satellites']}", flush=True)
        print(f"   Timestamp   : {timestamp}", flush=True)

        return True

    except sqlite3.Error as exc:
        conn.rollback()
        print(f"\n❌ SQLite insert failed: {exc}", flush=True)
        return False
    finally:
        conn.close()


# ============================================================
# ADS1115
# ============================================================
ADS_AVAILABLE = False
ADS_ERROR = ""

try:
    import board
    import busio
    import adafruit_ads1x15.ads1115 as ADS
    from adafruit_ads1x15.analog_in import AnalogIn

    i2c = busio.I2C(board.SCL, board.SDA)
    ads = ADS.ADS1115(i2c)
    ads.gain = 1

    # Numeric channels are intentional.
    bp_channel = AnalogIn(ads, 0)
    fp_channel = AnalogIn(ads, 1)
    cr_channel = AnalogIn(ads, 2)
    bc_channel = AnalogIn(ads, 3)

    ADS_AVAILABLE = True

except Exception as exc:
    ADS_ERROR = str(exc)


def read_pressure():
    if not ADS_AVAILABLE:
        return None

    try:
        return (
            bp_channel.value,
            fp_channel.value,
            cr_channel.value,
            bc_channel.value,
        )
    except Exception as exc:
        print(f"\n⚠️ ADS1115 read error: {exc}", flush=True)
        return None


# ============================================================
# EC200U SERIAL
# ============================================================
def close_modem():
    global ser, modem_connected, gnss_enabled

    with serial_lock:
        try:
            if ser is not None:
                ser.close()
        except Exception:
            pass
        ser = None

    modem_connected = False
    gnss_enabled = False


def send_at(command, timeout=3.0):
    global ser

    if ser is None:
        return ""

    try:
        with serial_lock:
            ser.reset_input_buffer()
            ser.write((command + "\r\n").encode())
            ser.flush()

            end = time.time() + timeout
            data = []

            while time.time() < end:
                if ser.in_waiting:
                    data.append(
                        ser.read(ser.in_waiting).decode(
                            errors="ignore"
                        )
                    )

                    text = "".join(data)

                    if (
                        "\r\nOK\r\n" in text
                        or "\nOK\n" in text
                        or "\r\nERROR\r\n" in text
                        or "\nERROR\n" in text
                    ):
                        break

                time.sleep(0.05)

            return "".join(data)

    except Exception as exc:
        print(f"\n⚠️ AT command failed [{command}]: {exc}", flush=True)
        close_modem()
        return ""


def open_modem():
    global ser, modem_connected

    try:
        close_modem()

        print(
            f"\n🔌 EC200U UART opening: {SERIAL_PORT} @ {BAUD_RATE}",
            flush=True
        )

        ser = serial.Serial(
            SERIAL_PORT,
            BAUD_RATE,
            timeout=SERIAL_TIMEOUT,
            write_timeout=SERIAL_TIMEOUT,
        )

        time.sleep(0.5)

        response = send_at("AT", 3)

        if response and "OK" in response.upper():
            modem_connected = True
            print("✅ EC200U responding", flush=True)
            return True

        print("❌ EC200U did not respond to AT", flush=True)
        close_modem()
        return False

    except Exception as exc:
        print(f"❌ EC200U UART error: {exc}", flush=True)
        close_modem()
        return False


def modem_is_alive():
    global modem_connected

    if ser is None:
        modem_connected = False
        return False

    response = send_at("AT", 2)

    if response and "OK" in response.upper():
        modem_connected = True
        return True

    modem_connected = False
    return False


# ============================================================
# GSM
# ============================================================
def parse_csq(response):
    match = re.search(r"\+CSQ:\s*(\d+)\s*,\s*(\d+)", response)

    if not match:
        return None, None

    rssi = int(match.group(1))

    if rssi == 99:
        return rssi, None

    return rssi, -113 + (2 * rssi)


def parse_qping(response):
    match = re.search(
        r'\+QPING:\s*\d+\s*,\s*"[^"]+"\s*,\s*\d+\s*,\s*([0-9.]+)',
        response,
    )

    if match:
        try:
            return float(match.group(1))
        except ValueError:
            pass

    match = re.search(
        r"(?:time|latency)\s*[=:]\s*([0-9.]+)",
        response,
        re.IGNORECASE,
    )

    if match:
        try:
            return float(match.group(1))
        except ValueError:
            pass

    return None


def update_gsm_information(verbose=False):
    if not modem_is_alive():
        gsm_info["gsm_status"] = "Disconnected"
        gsm_info["network_status"] = "UNKNOWN"
        gsm_info["latency_ms"] = None
        return False

    gsm_info["gsm_status"] = "Connected"

    cpin = send_at("AT+CPIN?", 3)
    gsm_info["sim_status"] = (
        "READY" if "+CPIN: READY" in cpin.upper()
        else "NOT READY"
    )

    ccid = send_at("AT+QCCID", 3)
    match = re.search(r"\+QCCID:\s*([0-9]+)", ccid)
    gsm_info["sim_iccid"] = match.group(1) if match else None

    cnum = send_at("AT+CNUM", 3)
    match = re.search(
        r'\+CNUM:\s*"[^"]*"\s*,\s*"([^"]+)"',
        cnum,
    )
    gsm_info["mobile_number"] = match.group(1) if match else None

    csq = send_at("AT+CSQ", 3)
    rssi, dbm = parse_csq(csq)
    gsm_info["signal_strength"] = rssi
    gsm_info["signal_dbm"] = dbm

    creg = send_at("AT+CREG?", 3)
    match = re.search(
        r"\+CREG:\s*\d+\s*,\s*(\d+)",
        creg,
    )
    registration = match.group(1) if match else None

    gsm_info["network_status"] = (
        "REGISTERED"
        if registration in ("1", "5")
        else "NOT REGISTERED"
    )

    cops = send_at("AT+COPS?", 5)
    match = re.search(
        r'\+COPS:\s*\d+\s*,\s*\d+\s*,\s*"([^"]+)"',
        cops,
    )
    gsm_info["operator"] = match.group(1) if match else None

    if gsm_info["network_status"] == "REGISTERED":
        ping = send_at(
            'AT+QPING=1,"8.8.8.8",5,1',
            8,
        )
        gsm_info["latency_ms"] = parse_qping(ping)
    else:
        gsm_info["latency_ms"] = None

    if verbose:
        print("\n📡 GSM INFORMATION", flush=True)
        print(f"   GSM Status    : {gsm_info['gsm_status']}", flush=True)
        print(f"   SIM Status    : {gsm_info['sim_status']}", flush=True)
        print(f"   ICCID         : {gsm_info['sim_iccid']}", flush=True)
        print(f"   Mobile Number : {gsm_info['mobile_number']}", flush=True)
        print(f"   Signal RSSI   : {gsm_info['signal_strength']}", flush=True)
        print(f"   Signal dBm    : {gsm_info['signal_dbm']}", flush=True)
        print(f"   Network       : {gsm_info['network_status']}", flush=True)
        print(f"   Operator      : {gsm_info['operator']}", flush=True)
        print(f"   Latency       : {gsm_info['latency_ms']} ms", flush=True)

    return True


# ============================================================
# GNSS
# ============================================================
def ensure_gnss():
    global gnss_enabled

    if not modem_is_alive():
        return False

    response = send_at("AT+QGPS?", 3)

    if re.search(r"\+QGPS:\s*1", response):
        gnss_enabled = True
        return True

    print("🛰️ GNSS not enabled. Starting GNSS...", flush=True)

    response = send_at("AT+QGPS=1", 5)

    if "OK" in response.upper():
        gnss_enabled = True
        print("🛰️✅ GNSS enabled", flush=True)
        return True

    response = send_at("AT+QGPS?", 3)

    if re.search(r"\+QGPS:\s*1", response):
        gnss_enabled = True
        print("🛰️✅ GNSS already enabled", flush=True)
        return True

    gnss_enabled = False
    return False


def parse_gga(response):
    match = re.search(
        r"\$(?:GP|GN)GGA,([^\r\n]+)",
        response,
    )

    if not match:
        return None

    fields = match.group(1).split(",")

    if len(fields) < 9:
        return None

    utc = fields[0]
    lat_raw = fields[1]
    lat_dir = fields[2]
    lon_raw = fields[3]
    lon_dir = fields[4]
    fix_quality = fields[5]
    satellites_raw = fields[6]
    altitude_raw = fields[8]

    satellites = (
        int(satellites_raw)
        if satellites_raw.isdigit()
        else None
    )

    if fix_quality in ("", "0"):
        return {
            "gnss_status": "NO FIX",
            "latitude": None,
            "longitude": None,
            "altitude_m": None,
            "satellites": satellites,
            "gps_utc": utc or None,
        }

    try:
        lat = float(lat_raw)
        lon = float(lon_raw)

        lat = int(lat / 100) + ((lat % 100) / 60.0)
        lon = int(lon / 100) + ((lon % 100) / 60.0)

        if lat_dir == "S":
            lat = -lat
        if lon_dir == "W":
            lon = -lon

        altitude = float(altitude_raw) if altitude_raw else None

        return {
            "gnss_status": "FIX",
            "latitude": lat,
            "longitude": lon,
            "altitude_m": altitude,
            "satellites": satellites,
            "gps_utc": utc or None,
        }

    except (ValueError, TypeError):
        return None


def parse_qgpsloc(response):
    match = re.search(
        r"\+QGPSLOC:\s*([^\r\n]+)",
        response,
    )

    if not match:
        return None

    fields = [
        x.strip()
        for x in match.group(1).split(",")
    ]

    if len(fields) < 5:
        return None

    try:
        return {
            "gnss_status": "FIX",
            "latitude": float(fields[1]),
            "longitude": float(fields[2]),
            "altitude_m": float(fields[4]),
            "satellites": None,
            "gps_utc": fields[0] or None,
        }
    except (ValueError, TypeError):
        return None


def read_gnss():
    global gnss_info

    if not modem_is_alive():
        gnss_info = {
            "gnss_status": "NO FIX",
            "latitude": None,
            "longitude": None,
            "altitude_m": None,
            "satellites": None,
            "gps_utc": None,
        }
        return False

    if not ensure_gnss():
        return False

    print("\n🛰️ Checking GNSS...", flush=True)

    loc_response = send_at("AT+QGPSLOC=0", 5)
    location = parse_qgpsloc(loc_response)

    gga_response = send_at(
        'AT+QGPSGNMEA="GGA"',
        5,
    )
    gga = parse_gga(gga_response)

    if gga and gga["gnss_status"] == "FIX":

        if location:
            gga["latitude"] = location["latitude"]
            gga["longitude"] = location["longitude"]
            gga["altitude_m"] = location["altitude_m"]
            gga["gps_utc"] = (
                location["gps_utc"]
                or gga["gps_utc"]
            )

        gnss_info = gga

    elif location:
        gnss_info = location

    else:
        gnss_info = {
            "gnss_status": "NO FIX",
            "latitude": None,
            "longitude": None,
            "altitude_m": None,
            "satellites": (
                gga["satellites"] if gga else None
            ),
            "gps_utc": (
                gga["gps_utc"] if gga else None
            ),
        }

    if gnss_info["gnss_status"] == "FIX":
        print(
            "📍 GNSS FIX | "
            f"LAT={gnss_info['latitude']:.7f} | "
            f"LON={gnss_info['longitude']:.7f} | "
            f"ALT={gnss_info['altitude_m']} m | "
            f"SAT={gnss_info['satellites']}",
            flush=True,
        )
        return True

    print(
        "📍 GNSS NO FIX | LAT=None | LON=None | "
        f"SAT={gnss_info['satellites']}",
        flush=True,
    )
    return False


# ============================================================
# STARTUP
# ============================================================
def startup():
    print("\n" + "=" * 75)
    print(f"✅ Device ID = {DEVICE_ID}")
    print("=" * 75)

    print("\n🔍 Checking ADS1115 I²C connection...", flush=True)

    if ADS_AVAILABLE:
        print("✅ ADS1115 I²C connected", flush=True)
    else:
        print(
            f"❌ ADS1115 I²C not connected: {ADS_ERROR}",
            flush=True,
        )

    print("\n🔌 Initializing EC200U...", flush=True)

    if open_modem():

        print("\n📟 EC200U INFORMATION", flush=True)

        ati = send_at("ATI", 5)
        if ati:
            print(ati.strip(), flush=True)

        imei_response = send_at("AT+CGSN", 5)
        imei_match = re.search(
            r"\b\d{14,17}\b",
            imei_response,
        )

        if imei_match:
            print(
                f"   IMEI          : {imei_match.group(0)}",
                flush=True,
            )

        print(
            "\n🛰️ Starting / checking GNSS...",
            flush=True,
        )

        ensure_gnss()

        print(
            "\n📡 Updating GSM information...",
            flush=True,
        )

        update_gsm_information(verbose=True)

    else:
        print(
            "⚠️ EC200U unavailable. "
            "Pressure logging will continue offline.",
            flush=True,
        )

    print("\n" + "=" * 75)
    print("🚀 Capture system started")
    print("=" * 75)
    print(f"📊 RAW_THRESHOLD = {RAW_THRESHOLD}", flush=True)
    print(f"⏱ READ_INTERVAL = {READ_INTERVAL} sec", flush=True)
    print(
        f"📡 GSM interval = {GSM_UPDATE_INTERVAL} sec",
        flush=True,
    )
    print(
        f"🛰️ GNSS interval = {GNSS_UPDATE_INTERVAL} sec",
        flush=True,
    )
    print("=" * 75)


# ============================================================
# MAIN
# ============================================================
def main():
    global first_pressure_stored
    global first_gnss_fix_stored
    global last_raw
    global last_modem_check
    global last_modem_reconnect
    global last_gsm_update
    global last_gnss_update
    global last_status_print
    global modem_connected

    initialize_database()
    startup()

    now = time.time()
    last_modem_check = now
    last_modem_reconnect = 0
    last_gsm_update = now
    last_gnss_update = now
    last_status_print = 0

    while True:

        loop_time = time.time()

        # ----------------------------------------------------
        # EC200U HEALTH / AUTO RECOVERY
        # ----------------------------------------------------
        if loop_time - last_modem_check >= MODEM_CHECK_INTERVAL:

            last_modem_check = loop_time

            if not modem_is_alive():

                modem_connected = False

                if (
                    loop_time - last_modem_reconnect
                    >= MODEM_RECONNECT_INTERVAL
                ):

                    last_modem_reconnect = loop_time

                    print(
                        "\n🔄 EC200U disconnected. "
                        "Trying automatic reconnect...",
                        flush=True,
                    )

                    if open_modem():

                        print(
                            "✅ EC200U recovered",
                            flush=True,
                        )

                        print(
                            "🛰️ Checking/restarting GNSS...",
                            flush=True,
                        )

                        ensure_gnss()
                        update_gsm_information(verbose=False)

        # ----------------------------------------------------
        # GSM UPDATE
        # ----------------------------------------------------
        if loop_time - last_gsm_update >= GSM_UPDATE_INTERVAL:

            last_gsm_update = loop_time

            if modem_connected:
                update_gsm_information(verbose=False)

        # ----------------------------------------------------
        # GNSS UPDATE
        # ----------------------------------------------------
        if loop_time - last_gnss_update >= GNSS_UPDATE_INTERVAL:

            last_gnss_update = loop_time
            read_gnss()

        # ----------------------------------------------------
        # PRESSURE READ
        # ----------------------------------------------------
        current_raw = read_pressure()

        if current_raw is None:
            time.sleep(0.5)
            continue

        timestamp = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        # ====================================================
        # 1. FIRST PRESSURE READING -> STORE
        # ====================================================
        if not first_pressure_stored:

            print(
                "\n📌 FIRST PRESSURE READING",
                flush=True,
            )

            print(
                f"   BP_raw = {current_raw[0]}",
                flush=True,
            )
            print(
                f"   FP_raw = {current_raw[1]}",
                flush=True,
            )
            print(
                f"   CR_raw = {current_raw[2]}",
                flush=True,
            )
            print(
                f"   BC_raw = {current_raw[3]}",
                flush=True,
            )

            success = insert_record(
                current_raw,
                timestamp,
                "FIRST PRESSURE",
            )

            if success:

                # ONLY a pressure record updates last_raw.
                last_raw = current_raw
                first_pressure_stored = True

                print(
                    "✅ FIRST PRESSURE READING STORED",
                    flush=True,
                )

        else:

            # =================================================
            # 2. FIRST GNSS FIX -> ONE ADDITIONAL RECORD
            # =================================================
            if (
                not first_gnss_fix_stored
                and gnss_info["gnss_status"] == "FIX"
            ):

                print(
                    "\n🛰️ FIRST GNSS FIX RECEIVED",
                    flush=True,
                )

                print(
                    "📥 Storing ONE additional GNSS record...",
                    flush=True,
                )

                success = insert_record(
                    current_raw,
                    timestamp,
                    "FIRST GNSS FIX",
                )

                if success:

                    first_gnss_fix_stored = True

                    # VERY IMPORTANT:
                    # GNSS-only record does NOT change last_raw.

                    print(
                        "✅ First GNSS record stored",
                        flush=True,
                    )

            # =================================================
            # 3. PRESSURE THRESHOLD
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

            pressure_changed = (
                bp_diff >= RAW_THRESHOLD
                or fp_diff >= RAW_THRESHOLD
                or cr_diff >= RAW_THRESHOLD
                or bc_diff >= RAW_THRESHOLD
            )

            if pressure_changed:

                print(
                    "\n⚠️ PRESSURE CHANGE DETECTED",
                    flush=True,
                )

                print(
                    f"   BP difference = {bp_diff}",
                    flush=True,
                )
                print(
                    f"   FP difference = {fp_diff}",
                    flush=True,
                )
                print(
                    f"   CR difference = {cr_diff}",
                    flush=True,
                )
                print(
                    f"   BC difference = {bc_diff}",
                    flush=True,
                )

                success = insert_record(
                    current_raw,
                    timestamp,
                    "PRESSURE CHANGE",
                )

                if success:

                    # Update reference ONLY after successful
                    # pressure DB insertion.
                    last_raw = current_raw

        # ====================================================
        # 4. CONTINUOUS STATUS EVERY SECOND
        # ====================================================
        if time.time() - last_status_print >= 1.0:

            last_status_print = time.time()

            print(
                f"device_id={DEVICE_ID}, "
                f"BP_raw={current_raw[0]}, "
                f"FP_raw={current_raw[1]}, "
                f"CR_raw={current_raw[2]}, "
                f"BC_raw={current_raw[3]}, "
                f"GNSS={gnss_info['gnss_status']}, "
                f"LAT={gnss_info['latitude']}, "
                f"LON={gnss_info['longitude']}, "
                f"SAT={gnss_info['satellites']}, "
                f"GSM={gsm_info['gsm_status']}, "
                f"RSSI={gsm_info['signal_strength']}, "
                f"dBm={gsm_info['signal_dbm']}, "
                f"Network={gsm_info['network_status']}, "
                f"Latency={gsm_info['latency_ms']} ms, "
                f"Timestamp={timestamp}",
                flush=True,
            )

        time.sleep(READ_INTERVAL)


# ============================================================
# ENTRY POINT
# ============================================================
if __name__ == "__main__":

    try:
        DEVICE_ID = get_device_id()
        main()

    except KeyboardInterrupt:
        print(
            "\n\n🛑 Capture system stopped by user.",
            flush=True,
        )

    except Exception as exc:
        print(
            f"\n❌ FATAL ERROR: {exc}",
            flush=True,
        )

    finally:
        close_modem()
        print(
            "🔌 EC200U connection closed.",
            flush=True,
        )
'''

path = Path("/mnt/data/GSM_Capture1_corrected.py")
path.write_text(code, encoding="utf-8")
print(f"Created corrected file: {path}")
