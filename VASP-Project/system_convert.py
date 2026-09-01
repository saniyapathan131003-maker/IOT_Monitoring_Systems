import sqlite3
import time
import os
import sys

# ---------------- ENCODING ----------------
sys.stdout.reconfigure(encoding='utf-8')

# ---------------- PATH SETUP ----------------
BASE_DIR = "/app" if os.path.exists("/app") else os.path.dirname(os.path.abspath(__file__))
DB_FOLDER = os.path.join(BASE_DIR, "db")
DB_PATH = os.path.join(DB_FOLDER, "project.db")

os.makedirs(DB_FOLDER, exist_ok=True)

print(f"Database file: {DB_PATH}", flush=True)

# ---------------- DATABASE SETUP ----------------
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
conn.row_factory = sqlite3.Row
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

# ---------------- ADS1115 SETUP ----------------
ADS_AVAILABLE = True

try:
    import board
    import busio
    import adafruit_ads1x15.ads1115 as ADS
    from adafruit_ads1x15.analog_in import AnalogIn

    i2c = busio.I2C(board.SCL, board.SDA)
    ads = ADS.ADS1115(i2c)
    ads.gain = 1   # ±4.096V

    bp_channel = AnalogIn(ads, 0)
    fp_channel = AnalogIn(ads, 1)
    cr_channel = AnalogIn(ads, 2)
    bc_channel = AnalogIn(ads, 3)

except Exception as e:
    print("⚠️ ADS1115 not detected. Using dummy values.", flush=True)
    ADS_AVAILABLE = False

# ---------------- CONSTANTS ----------------
FULL_SCALE_VOLTAGE = 4.096
ADC_MAX = 32767
RESISTOR = 160.0
PRESSURE_RANGE = 10.0   # 0–10 bar

# ---------------- SENSOR FUNCTIONS ----------------
def read_raw_values():
    if ADS_AVAILABLE:
        return (
            bp_channel.value,
            fp_channel.value,
            cr_channel.value,
            bc_channel.value
        )
    else:
        return (0, 0, 0, 0)

def convert_to_pressure(raw):
    # Step 1: Raw -> Voltage
    voltage = (raw / ADC_MAX) * FULL_SCALE_VOLTAGE

    # Step 2: Voltage -> Current (mA)
    current_mA = (voltage / RESISTOR) * 1000

    # Step 3: 4–20mA -> Pressure
    pressure = ((current_mA - 4) / 16) * PRESSURE_RANGE

    # Clamp negative values
    if pressure < 0:
        pressure = 0

    return round(pressure, 2)

def get_pressures():
    raw_values = read_raw_values()
    pressures = tuple(convert_to_pressure(r) for r in raw_values)
    return raw_values, pressures

# ---------------- MAIN LOOP ----------------
print("\nSystem started... Logging every 10 seconds\n", flush=True)

while True:
    raw_values, pressures = get_pressures()

    cursor.execute("""
        SELECT bp_pressure, fp_pressure, cr_pressure, bc_pressure
        FROM brake_pressure_log
        ORDER BY id DESC
        LIMIT 1
    """)
    last = cursor.fetchone()

    if not last or any(abs(n - l) >= 0.5 for n, l in zip(pressures, last)):
        cursor.execute("""
            INSERT INTO brake_pressure_log
            (bp_pressure, fp_pressure, cr_pressure, bc_pressure)
            VALUES (?, ?, ?, ?)
        """, pressures)
        conn.commit()

    print(
        f"RAW VALUES\n"
        f"BP:{raw_values[0]} | FP:{raw_values[1]} | "
        f"CR:{raw_values[2]} | BC:{raw_values[3]}\n"
        f"PRESSURE VALUES\n"
        f"BP:{pressures[0]} bar | FP:{pressures[1]} bar | "
        f"CR:{pressures[2]} bar | BC:{pressures[3]} bar\n"
        f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        "---------------------------------------------",
        flush=True
    )

    time.sleep(10)
