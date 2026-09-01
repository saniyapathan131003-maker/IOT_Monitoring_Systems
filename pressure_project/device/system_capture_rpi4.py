# ---------------- IMPORTS ----------------
import time
import sys
import sqlite3
import os

# ---------------- ENCODING ----------------
sys.stdout.reconfigure(encoding='utf-8')

# ---------------- CONFIG ----------------
RAW_THRESHOLD = 1638       
READ_INTERVAL = 5          

# ---------------- DATABASE PATH ----------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.path.join(BASE_DIR, "db")
os.makedirs(DB_DIR, exist_ok=True)  # Ensure the db folder exists
DB_PATH = os.path.join(DB_DIR, "new_db.db")

# ---------------- DATABASE SETUP ----------------
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cursor = conn.cursor()

# Create table if it doesn't exist
cursor.execute("""
CREATE TABLE IF NOT EXISTS brake_pressure_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    BP_raw INTEGER,
    BC_raw INTEGER,
    FP_raw INTEGER,
    CR_raw INTEGER
)
""")
conn.commit()

# ---------------- ADS1115 SENSOR SETUP ----------------
ADS_AVAILABLE = True

try:
    import board
    import busio
    import adafruit_ads1x15.ads1115 as ADS
    from adafruit_ads1x15.analog_in import AnalogIn

    # Initialize I2C and ADS1115
    i2c = busio.I2C(board.SCL, board.SDA)
    ads = ADS.ADS1115(i2c)
    ads.gain = 1

    # Define analog channels
    bp_channel = AnalogIn(ads, 0)
    fp_channel = AnalogIn(ads, 1)
    cr_channel = AnalogIn(ads, 2)
    bc_channel = AnalogIn(ads, 3)

except Exception as e:
    ADS_AVAILABLE = False
    print(f"⚠️ ADS1115 not available: {e}", flush=True)

# ---------------- SENSOR READ FUNCTION ----------------
def read_raw_values():
    if ADS_AVAILABLE:
        return (
            bp_channel.value,
            bc_channel.value,
            fp_channel.value,
            cr_channel.value
        )
    else:
        return (0, 0, 0, 0)

# ---------------- MAIN LOOP ----------------
print("🚀 System started...", flush=True)

last_raw = None

while True:
    current_raw = read_raw_values()
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')

    # Print raw values
    print(
        f"RAW VALUES | BP:{current_raw[0]} | BC:{current_raw[1]} | FP:{current_raw[2]} | CR:{current_raw[3]} | timestamp:{timestamp}",
        flush=True
    )

    upload = False

    # Insert first reading or if significant change occurs
    if last_raw is None:
        upload = True
    else:
        diffs = [abs(current_raw[i] - last_raw[i]) for i in range(4)]
        if any(diff >= RAW_THRESHOLD for diff in diffs):
            upload = True

    if upload:
        cursor.execute("""
            INSERT INTO brake_pressure_log (BP_raw, BC_raw, FP_raw, CR_raw)
            VALUES (?, ?, ?, ?)
        """, (*current_raw,))
        conn.commit()
        last_raw = current_raw
        print(f"✅ Data inserted into DB at {timestamp}", flush=True)
    else:
        print("⏭ No significant change → Skipped insert", flush=True)

    print("---------------------------------------------\n", flush=True)
    time.sleep(READ_INTERVAL)
