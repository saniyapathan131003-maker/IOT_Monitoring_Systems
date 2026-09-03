#!/usr/bin/env python3

import time
import sys
import sqlite3
import os
import threading

# ============================================================
# OPTIONAL: SERIAL COMMUNICATION FOR EC200U
# ============================================================
try:
    import serial
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False

# ---------------- ENCODING ----------------
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# ============================================================
# CONFIGURATION
# ============================================================

# Existing pressure capture settings
RAW_THRESHOLD = 326
READ_INTERVAL = 0.1

# EC200U UART
GSM_PORT = "/dev/ttyAMA3"
GSM_BAUDRATE = 115200
GSM_TIMEOUT = 3

# GSM information refresh interval
GSM_CHECK_INTERVAL = 60

# Cellular ping target
# This measures cellular/network latency, not your cloud API latency.
PING_HOST = "8.8.8.8"

# ============================================================
# DATABASE PATH
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DB_DIR = os.path.join(BASE_DIR, "db")
os.makedirs(DB_DIR, exist_ok=True)

DB_PATH = os.path.join(DB_DIR, "new_db.db")

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
# CREATE SENSOR TABLE
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

    uploaded INTEGER DEFAULT 0,

    gsm_status TEXT,
    sim_status TEXT,
    sim_iccid TEXT,
    mobile_number TEXT,

    signal_strength INTEGER,
    signal_dbm INTEGER,

    network_status TEXT,
    operator TEXT,

    latency_ms INTEGER

)
""")

conn.commit()

# ============================================================
# DATABASE MIGRATION
# Add new columns if old table already exists
# ============================================================

existing_columns = set()

cursor.execute("PRAGMA table_info(brake_pressure_log)")

for column in cursor.fetchall():
    existing_columns.add(column["name"])

new_columns = {

    "gsm_status": "TEXT",
    "sim_status": "TEXT",
    "sim_iccid": "TEXT",
    "mobile_number": "TEXT",

    "signal_strength": "INTEGER",
    "signal_dbm": "INTEGER",

    "network_status": "TEXT",
    "operator": "TEXT",

    "latency_ms": "INTEGER"
}

for column_name, column_type in new_columns.items():

    if column_name not in existing_columns:

        try:
            cursor.execute(
                f"ALTER TABLE brake_pressure_log "
                f"ADD COLUMN {column_name} {column_type}"
            )

            print(
                f"✅ Added database column: {column_name}",
                flush=True
            )

        except Exception as e:

            print(
                f"⚠️ Could not add column {column_name}: {e}",
                flush=True
            )

conn.commit()

# ============================================================
# FETCH DEVICE ID
# ============================================================

DEVICE_ID = "UNKNOWN"

try:

    cursor.execute(
        "SELECT device_id FROM device_config LIMIT 1"
    )

    DEVICE_ROW = cursor.fetchone()

    if DEVICE_ROW and DEVICE_ROW["device_id"]:

        DEVICE_ID = DEVICE_ROW["device_id"]

        print(
            f"✅ Device ID = {DEVICE_ID}\n",
            flush=True
        )

    else:

        print(
            "⚠️ Device ID missing! Using UNKNOWN.",
            flush=True
        )

except Exception as e:

    print(
        f"⚠️ Device ID could not be read: {e}",
        flush=True
    )

# ============================================================
# ADS1115 SENSOR INITIALIZATION
# ============================================================

ADS_AVAILABLE = True

try:

    import board
    import busio

    import adafruit_ads1x15.ads1115 as ADS

    from adafruit_ads1x15.analog_in import AnalogIn

    # I2C
    i2c = busio.I2C(
        board.SCL,
        board.SDA
    )

    # ADS1115
    ads = ADS.ADS1115(i2c)

    # Gain 1
    ads.gain = 1

    # Channels
    bp_channel = AnalogIn(ads, 0)
    fp_channel = AnalogIn(ads, 1)
    cr_channel = AnalogIn(ads, 2)
    bc_channel = AnalogIn(ads, 3)

    print(
        "✅ ADS1115 sensor detected and initialized.",
        flush=True
    )

except Exception as e:

    ADS_AVAILABLE = False

    print(
        f"⚠️ ADS1115 sensor not detected! ({e})",
        flush=True
    )

# ============================================================
# SENSOR READ FUNCTION
# ============================================================

def read_raw_values():

    if ADS_AVAILABLE:

        return (
            bp_channel.value,
            fp_channel.value,
            cr_channel.value,
            bc_channel.value
        )

    return (0, 0, 0, 0)


# ============================================================
# GSM CLASS
# ============================================================

class EC200U:

    def __init__(self, port, baudrate, timeout):

        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout

        self.ser = None

        self.lock = threading.Lock()

    # --------------------------------------------------------
    # OPEN SERIAL PORT
    # --------------------------------------------------------

    def connect(self):

        if not SERIAL_AVAILABLE:

            print(
                "⚠️ pyserial is not installed.",
                flush=True
            )

            return False

        try:

            self.ser = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=self.timeout,
                write_timeout=self.timeout
            )

            time.sleep(1)

            print(
                f"📡 EC200U UART connected: {self.port}",
                flush=True
            )

            return True

        except Exception as e:

            print(
                f"⚠️ EC200U UART connection failed: {e}",
                flush=True
            )

            self.ser = None

            return False

    # --------------------------------------------------------
    # SEND AT COMMAND
    # --------------------------------------------------------

    def command(self, command, wait_time=1):

        if self.ser is None:

            return ""

        with self.lock:

            try:

                # Clear old data
                self.ser.reset_input_buffer()

                # Send command
                self.ser.write(
                    (command + "\r\n").encode()
                )

                self.ser.flush()

                time.sleep(wait_time)

                response = self.ser.read_all().decode(
                    errors="ignore"
                )

                return response.strip()

            except Exception as e:

                print(
                    f"⚠️ GSM command error [{command}]: {e}",
                    flush=True
                )

                return ""

    # --------------------------------------------------------
    # CHECK BASIC COMMUNICATION
    # --------------------------------------------------------

    def check_connection(self):

        response = self.command(
            "AT",
            wait_time=0.5
        )

        return "OK" in response

    # --------------------------------------------------------
    # SIM STATUS
    # --------------------------------------------------------

    def get_sim_status(self):

        response = self.command(
            "AT+CPIN?",
            wait_time=0.5
        )

        if "+CPIN: READY" in response:

            return "READY"

        if "+CPIN:" in response:

            try:

                line = [
                    x for x in response.splitlines()
                    if "+CPIN:" in x
                ][0]

                return line.split(":", 1)[1].strip()

            except Exception:
                return "UNKNOWN"

        return "UNKNOWN"

    # --------------------------------------------------------
    # SIM ICCID
    # --------------------------------------------------------

    def get_iccid(self):

        response = self.command(
            "AT+QCCID",
            wait_time=0.5
        )

        for line in response.splitlines():

            line = line.strip()

            if line.startswith("+QCCID:"):

                return line.split(":", 1)[1].strip()

        return ""

    # --------------------------------------------------------
    # MOBILE NUMBER
    # --------------------------------------------------------

    def get_mobile_number(self):

        response = self.command(
            "AT+CNUM",
            wait_time=0.7
        )

        for line in response.splitlines():

            line = line.strip()

            if line.startswith("+CNUM:"):

                try:

                    data = line.split(":", 1)[1]

                    parts = data.split(",")

                    if len(parts) >= 2:

                        number = parts[1].strip()

                        number = number.replace(
                            '"',
                            ""
                        )

                        if number:
                            return number

                except Exception:
                    pass

        return ""

    # --------------------------------------------------------
    # SIGNAL STRENGTH
    # --------------------------------------------------------

    def get_signal(self):

        response = self.command(
            "AT+CSQ",
            wait_time=0.5
        )

        for line in response.splitlines():

            line = line.strip()

            if line.startswith("+CSQ:"):

                try:

                    data = line.split(":", 1)[1]

                    parts = data.split(",")

                    csq = int(parts[0].strip())

                    if csq == 99:

                        return None, None

                    # 3GPP approximate RSSI conversion
                    dbm = -113 + (2 * csq)

                    return csq, dbm

                except Exception:
                    pass

        return None, None

    # --------------------------------------------------------
    # NETWORK REGISTRATION
    # --------------------------------------------------------

    def get_network_status(self):

        response = self.command(
            "AT+CREG?",
            wait_time=0.5
        )

        for line in response.splitlines():

            line = line.strip()

            if line.startswith("+CREG:"):

                try:

                    data = line.split(":", 1)[1]

                    parts = [
                        x.strip()
                        for x in data.split(",")
                    ]

                    status_code = parts[-1]

                    status_map = {

                        "0": "Not registered",
                        "1": "Registered",
                        "2": "Searching",
                        "3": "Registration denied",
                        "4": "Unknown",
                        "5": "Registered roaming"
                    }

                    return status_map.get(
                        status_code,
                        f"Unknown ({status_code})"
                    )

                except Exception:
                    pass

        return "Unknown"

    # --------------------------------------------------------
    # OPERATOR
    # --------------------------------------------------------

    def get_operator(self):

        response = self.command(
            "AT+COPS?",
            wait_time=1
        )

        for line in response.splitlines():

            line = line.strip()

            if line.startswith("+COPS:"):

                try:

                    data = line.split(":", 1)[1]

                    parts = data.split(",")

                    # Format:
                    # +COPS: 0,0,"Jio",7

                    if len(parts) >= 3:

                        operator = parts[2].strip()

                        operator = operator.replace(
                            '"',
                            ""
                        )

                        return operator

                except Exception:
                    pass

        return ""

    # --------------------------------------------------------
    # CELLULAR PING LATENCY
    # --------------------------------------------------------

    def get_latency(self):

        # EC200U QPING
        command = (
            f'AT+QPING=1,"{PING_HOST}",'
            f'5,1'
        )

        response = self.command(
            command,
            wait_time=6
        )

        # Example:
        # +QPING: 0,"8.8.8.8",32,45,64
        #
        # The 4th value is normally latency.

        for line in response.splitlines():

            line = line.strip()

            if "+QPING:" in line:

                try:

                    data = line.split(":", 1)[1]

                    parts = [
                        x.strip()
                        for x in data.split(",")
                    ]

                    if len(parts) >= 4:

                        ping_time = parts[3]

                        ping_time = ping_time.replace(
                            '"',
                            ""
                        )

                        return int(
                            float(ping_time)
                        )

                except Exception:
                    pass

        return None

    # --------------------------------------------------------
    # COMPLETE GSM INFORMATION
    # --------------------------------------------------------

    def get_all_status(self):

        status = {

            "gsm_status": "Disconnected",

            "sim_status": "UNKNOWN",

            "sim_iccid": "",

            "mobile_number": "",

            "signal_strength": None,

            "signal_dbm": None,

            "network_status": "Unknown",

            "operator": "",

            "latency_ms": None
        }

        # Check modem
        if not self.check_connection():

            return status

        status["gsm_status"] = "Connected"

        # SIM
        status["sim_status"] = self.get_sim_status()

        # ICCID
        if status["sim_status"] == "READY":

            status["sim_iccid"] = self.get_iccid()

            status["mobile_number"] = (
                self.get_mobile_number()
            )

        # Signal
        (
            status["signal_strength"],
            status["signal_dbm"]
        ) = self.get_signal()

        # Network
        status["network_status"] = (
            self.get_network_status()
        )

        # Operator
        status["operator"] = (
            self.get_operator()
        )

        # Latency
        if (
            status["network_status"]
            in ["Registered", "Registered roaming"]
        ):

            status["latency_ms"] = (
                self.get_latency()
            )

        return status


# ============================================================
# GSM INITIALIZATION
# ============================================================

gsm = EC200U(
    GSM_PORT,
    GSM_BAUDRATE,
    GSM_TIMEOUT
)

gsm_connected = gsm.connect()

# ============================================================
# INITIAL GSM STATUS
# ============================================================

gsm_status_data = {

    "gsm_status": "Disconnected",

    "sim_status": "UNKNOWN",

    "sim_iccid": "",

    "mobile_number": "",

    "signal_strength": None,

    "signal_dbm": None,

    "network_status": "Unknown",

    "operator": "",

    "latency_ms": None
}

last_gsm_check = 0

# ============================================================
# DISPLAY INITIAL GSM STATUS
# ============================================================

if gsm_connected:

    print(
        "\n📡 Checking EC200U GSM status...",
        flush=True
    )

    try:

        gsm_status_data = gsm.get_all_status()

        print(
            f"   GSM        : "
            f"{gsm_status_data['gsm_status']}",
            flush=True
        )

        print(
            f"   SIM        : "
            f"{gsm_status_data['sim_status']}",
            flush=True
        )

        print(
            f"   ICCID      : "
            f"{gsm_status_data['sim_iccid'] or 'Not available'}",
            flush=True
        )

        print(
            f"   Mobile No. : "
            f"{gsm_status_data['mobile_number'] or 'Not available'}",
            flush=True
        )

        print(
            f"   CSQ        : "
            f"{gsm_status_data['signal_strength']}",
            flush=True
        )

        print(
            f"   Signal     : "
            f"{gsm_status_data['signal_dbm']} dBm",
            flush=True
        )

        print(
            f"   Network    : "
            f"{gsm_status_data['network_status']}",
            flush=True
        )

        print(
            f"   Operator   : "
            f"{gsm_status_data['operator'] or 'Unknown'}",
            flush=True
        )

        print(
            f"   Latency    : "
            f"{gsm_status_data['latency_ms']} ms\n",
            flush=True
        )

    except Exception as e:

        print(
            f"⚠️ GSM status read failed: {e}",
            flush=True
        )


last_gsm_check = time.time()

# ============================================================
# MAIN CAPTURE LOOP
# ============================================================

print(
    "🚀 Capture system started...\n",
    flush=True
)

last_raw = None

try:

    while True:

        # ====================================================
        # GSM STATUS UPDATE
        # ====================================================

        current_time = time.time()

        if (
            current_time - last_gsm_check
            >= GSM_CHECK_INTERVAL
        ):

            if gsm.ser is None:

                gsm.connect()

            if gsm.ser is not None:

                try:

                    gsm_status_data = (
                        gsm.get_all_status()
                    )

                except Exception as e:

                    print(
                        f"⚠️ GSM status update failed: {e}",
                        flush=True
                    )

            else:

                gsm_status_data = {

                    "gsm_status": "Disconnected",

                    "sim_status": "UNKNOWN",

                    "sim_iccid": "",

                    "mobile_number": "",

                    "signal_strength": None,

                    "signal_dbm": None,

                    "network_status": "Unknown",

                    "operator": "",

                    "latency_ms": None
                }

            print(
                "\n📡 GSM STATUS UPDATE",
                flush=True
            )

            print(
                f"   GSM        : "
                f"{gsm_status_data['gsm_status']}",
                flush=True
            )

            print(
                f"   SIM        : "
                f"{gsm_status_data['sim_status']}",
                flush=True
            )

            print(
                f"   CSQ        : "
                f"{gsm_status_data['signal_strength']}",
                flush=True
            )

            print(
                f"   Signal     : "
                f"{gsm_status_data['signal_dbm']} dBm",
                flush=True
            )

            print(
                f"   Network    : "
                f"{gsm_status_data['network_status']}",
                flush=True
            )

            print(
                f"   Operator   : "
                f"{gsm_status_data['operator'] or 'Unknown'}",
                flush=True
            )

            print(
                f"   Latency    : "
                f"{gsm_status_data['latency_ms']} ms\n",
                flush=True
            )

            last_gsm_check = current_time

        # ====================================================
        # ADS1115 READ
        # ====================================================

        if ADS_AVAILABLE:

            current_raw = read_raw_values()

            ads_status = "Connected"

        else:

            current_raw = (
                0,
                0,
                0,
                0
            )

            ads_status = "Not connected"

        # ====================================================
        # TIMESTAMP
        # ====================================================

        timestamp = time.strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        # ====================================================
        # DISPLAY SENSOR DATA
        # ====================================================

        print(

            f"device_id = {DEVICE_ID}, "

            f"BP_raw = {current_raw[0]}, "
            f"FP_raw = {current_raw[1]}, "
            f"CR_raw = {current_raw[2]}, "
            f"BC_raw = {current_raw[3]}, "

            f"timestamp = {timestamp}, "

            f"ADS1115_status = {ads_status}, "

            f"GSM = {gsm_status_data['gsm_status']}, "

            f"SIM = {gsm_status_data['sim_status']}, "

            f"CSQ = {gsm_status_data['signal_strength']}, "

            f"Signal = {gsm_status_data['signal_dbm']} dBm, "

            f"Network = {gsm_status_data['network_status']}, "

            f"Latency = {gsm_status_data['latency_ms']} ms",

            flush=True
        )

        # ====================================================
        # EXISTING RAW VALUE LOGIC
        # ====================================================

        upload = False

        if last_raw is None:

            upload = True

        else:

            diffs = [

                abs(
                    current_raw[i]
                    - last_raw[i]
                )

                for i in range(4)
            ]

            if any(
                diff >= RAW_THRESHOLD
                for diff in diffs
            ):

                upload = True

        # ====================================================
        # INSERT INTO SQLITE
        # ====================================================

        if upload:

            try:

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

                        latency_ms
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
                        ?
                    )
                    """,

                    (

                        DEVICE_ID,

                        current_raw[0],
                        current_raw[1],
                        current_raw[2],
                        current_raw[3],

                        timestamp,

                        gsm_status_data[
                            "gsm_status"
                        ],

                        gsm_status_data[
                            "sim_status"
                        ],

                        gsm_status_data[
                            "sim_iccid"
                        ],

                        gsm_status_data[
                            "mobile_number"
                        ],

                        gsm_status_data[
                            "signal_strength"
                        ],

                        gsm_status_data[
                            "signal_dbm"
                        ],

                        gsm_status_data[
                            "network_status"
                        ],

                        gsm_status_data[
                            "operator"
                        ],

                        gsm_status_data[
                            "latency_ms"
                        ]
                    )
                )

                conn.commit()

                # Keep your existing logic:
                # last_raw changes only after insertion
                last_raw = current_raw

                print(
                    f"✅ Data inserted into DB at "
                    f"{timestamp}",
                    flush=True
                )

                print(
                    f"   GSM={gsm_status_data['gsm_status']} | "
                    f"SIM={gsm_status_data['sim_status']} | "
                    f"CSQ={gsm_status_data['signal_strength']} | "
                    f"{gsm_status_data['signal_dbm']} dBm | "
                    f"Network={gsm_status_data['network_status']} | "
                    f"Latency={gsm_status_data['latency_ms']} ms",
                    flush=True
                )

            except Exception as e:

                print(
                    f"❌ Database insert failed: {e}",
                    flush=True
                )

        else:

            print(
                "⏭ No significant change → "
                "Skipped insert\n",
                flush=True
            )

        # ====================================================
        # SENSOR READ INTERVAL
        # ====================================================

        time.sleep(READ_INTERVAL)
except KeyboardInterrupt:

    print(
        "\n🛑 Capture system stopped by user.",
        flush=True
    )

finally:

    try:

        if gsm.ser is not None:

            gsm.ser.close()

            print(
                "📡 EC200U UART closed.",
                flush=True
            )

    except Exception:
        pass

    try:

        conn.close()

        print(
            "💾 Database connection closed.",
            flush=True
        )

    except Exception:
        pass