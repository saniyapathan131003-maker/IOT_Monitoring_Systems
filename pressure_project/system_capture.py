import time
import sys
import sqlite3
import os

# ---------------- ENCODING ----------------
sys.stdout.reconfigure(encoding='utf-8')

# ---------------- CONFIG ----------------
RAW_THRESHOLD = 1638                 # ~0.5 bar equivalent
READ_INTERVAL = 0.3                   # seconds

# ---------------- DATABASE PATH ----------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "db", "project.db")

# ---------------- DATABASE ----------------
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS brake_pressure_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bp_pressure REAL,
    fp_pressure REAL,
    cr_pressure REAL,
    bc_pressure REAL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    uploaded INTEGER DEFAULT 0
)
""")
conn.commit()

# ---------------- ADS1115 SENSOR ----------------
ADS_AVAILABLE = True

try:
    import board
    import busio
    import adafruit_ads1x15.ads1115 as ADS
    from adafruit_ads1x15.analog_in import AnalogIn

    i2c = busio.I2C(board.SCL, board.SDA)
    ads = ADS.ADS1115(i2c)
    ads.gain = 1

    bp_channel = AnalogIn(ads, 0)
    fp_channel = AnalogIn(ads, 1)
    cr_channel = AnalogIn(ads, 2)
    bc_channel = AnalogIn(ads, 3)

except Exception:
    ADS_AVAILABLE = False

# ---------------- SENSOR READ FUNCTION ----------------
def read_raw_values():
    if ADS_AVAILABLE:
        return (
            bp_channel.value,
            fp_channel.value,
            cr_channel.value,
            bc_channel.value
        )
    return (0, 0, 0, 0)

# ---------------- MAIN LOOP ----------------
print("System started...\n", flush=True)

last_raw = None

while True:
    current_raw = read_raw_values()
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')

    print(
        f"RAW VALUES | "
        f"BP:{current_raw[0]} | FP:{current_raw[1]} "
        f"CR:{current_raw[2]} | BC:{current_raw[3]} | "
        f"timestamp : {timestamp}",
        flush=True
    )

    upload = False

    if last_raw is None:
        upload = True
    else:
        diffs = [abs(current_raw[i] - last_raw[i]) for i in range(4)]
        if any(diff >= RAW_THRESHOLD for diff in diffs):
            upload = True

    if upload:
        cursor.execute("""
            INSERT INTO brake_pressure_log
            (bp_pressure, fp_pressure, cr_pressure, bc_pressure)
            VALUES (?, ?, ?, ?)
        """, (*current_raw,))
        conn.commit()
        last_raw = current_raw
        print(f"✅ Data inserted into DB at {timestamp}", flush=True)
    else:
        print("⏭ No significant change → Skipped insert", flush=True)

    print("---------------------------------------------\n", flush=True)
    time.sleep(READ_INTERVAL)
