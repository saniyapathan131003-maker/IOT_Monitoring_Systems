import sqlite3
import time
import random
import sys
#from upload1 import upload_status  # import helper function

sys.stdout.reconfigure(encoding='utf-8')
DB_PATH = "project.db"  # database will be created in the same folder as thee.py
conn = sqlite3.connect(DB_PATH)
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


def generate_raw_sensors():
    return (
        random.uniform(0, 1023),
        random.uniform(0, 1023),
        random.uniform(0, 1023),
        random.uniform(0, 1023)
    )

def convert_to_pressure(raw_value):
    return round((raw_value / 1023) * 10, 2)

def generate_pressures():
    raw = generate_raw_sensors()
    return tuple(convert_to_pressure(r) for r in raw)

while True:
    new_pressures = generate_pressures()

    # Fetch last row
    cursor.execute("""
        SELECT bp_pressure, fp_pressure, cr_pressure, bc_pressure
        FROM brake_pressure_log
        ORDER BY id DESC
        LIMIT 1
    """)
    last = cursor.fetchone()

    if not last or any(abs(n - l) >= 0.5 for n, l in zip(new_pressures, last)):
        cursor.execute("""
            INSERT INTO brake_pressure_log
            (bp_pressure, fp_pressure, cr_pressure, bc_pressure)
            VALUES (?, ?, ?, ?)
        """, new_pressures)
        conn.commit()
        print(
            f"Inserted -> BP:{new_pressures[0]} | FP:{new_pressures[1]} | CR:{new_pressures[2]} | BC:{new_pressures[3]} | "
            f"Time:{time.strftime('%Y-%m-%d %H:%M:%S')}",
            flush=True
        )

        # Call from uploading status .
        #upload_status()
    else:
        print("No significant change, skipping...", flush=True)

    time.sleep(20)
