#!/usr/bin/env python3

import time
import sys
import sqlite3
import os

# ============================================================
# ENCODING
# ============================================================

sys.stdout.reconfigure(encoding="utf-8")


# ============================================================
# CONFIGURATION
# ============================================================

RAW_THRESHOLD = 326       # Pressure change threshold
READ_INTERVAL = 0.1       # Read every 100 ms


# ============================================================
# DATABASE PATH
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.path.join(BASE_DIR, "db")
DB_PATH = os.path.join(DB_DIR, "new_db.db")

os.makedirs(DB_DIR, exist_ok=True)


# ============================================================
# DATABASE CONNECTION
# ============================================================

conn = sqlite3.connect(
    DB_PATH,
    check_same_thread=False,
    timeout=30
)

conn.row_factory = sqlite3.Row

cursor = conn.cursor()

# Prevent SQLite "database is locked" problems
cursor.execute("PRAGMA journal_mode=WAL")
cursor.execute("PRAGMA busy_timeout=30000")


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
# FETCH DEVICE ID
# ============================================================

try:

    cursor.execute("""
        SELECT device_id
        FROM device_config
        LIMIT 1
    """)

    DEVICE_ROW = cursor.fetchone()

    if DEVICE_ROW and DEVICE_ROW["device_id"]:

        DEVICE_ID = DEVICE_ROW["device_id"]

        print("=" * 75, flush=True)
        print(
            f"✅ Device ID = {DEVICE_ID}",
            flush=True
        )
        print("=" * 75, flush=True)

    else:

        DEVICE_ID = "UNKNOWN"

        print(
            "⚠️ Device ID missing!",
            flush=True
        )

except sqlite3.Error as e:

    DEVICE_ID = "UNKNOWN"

    print(
        f"⚠️ Could not read device ID: {e}",
        flush=True
    )


# ============================================================
# ADS1115 INITIALIZATION
# ============================================================

ADS_AVAILABLE = False

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
    # Use numeric channel numbers.
    # Do NOT use ADS.P0 / ADS.P1 / etc.

    bp_channel = AnalogIn(ads, 0)
    fp_channel = AnalogIn(ads, 1)
    cr_channel = AnalogIn(ads, 2)
    bc_channel = AnalogIn(ads, 3)

    ADS_AVAILABLE = True

    print(
        "✅ ADS1115 sensor detected and initialized.",
        flush=True
    )

except Exception as e:

    ADS_AVAILABLE = False

    print(
        f"❌ ADS1115 initialization failed: {e}",
        flush=True
    )


# ============================================================
# READ PRESSURE VALUES
# ============================================================

def read_raw_values():

    if not ADS_AVAILABLE:
        return None

    try:

        bp = bp_channel.value
        fp = fp_channel.value
        cr = cr_channel.value
        bc = bc_channel.value

        return (
            bp,
            fp,
            cr,
            bc
        )

    except Exception as e:

        print(
            f"\n⚠️ ADS1115 read error: {e}",
            flush=True
        )

        return None


# ============================================================
# INSERT PRESSURE RECORD
# ============================================================

def insert_pressure_record(
    current_raw,
    timestamp
):

    try:

        cursor.execute("""
            INSERT INTO brake_pressure_log
            (
                device_id,
                BP_raw,
                FP_raw,
                CR_raw,
                BC_raw,
                timestamp,
                uploaded
            )
            VALUES (?, ?, ?, ?, ?, ?, 0)
        """, (
            DEVICE_ID,
            current_raw[0],
            current_raw[1],
            current_raw[2],
            current_raw[3],
            timestamp
        ))

        conn.commit()

        db_id = cursor.lastrowid

        print(
            "\n💾 PRESSURE RECORD STORED",
            flush=True
        )

        print(
            f"   DB ID       : {db_id}",
            flush=True
        )

        print(
            f"   Device ID   : {DEVICE_ID}",
            flush=True
        )

        print(
            f"   BP_raw      : {current_raw[0]}",
            flush=True
        )

        print(
            f"   FP_raw      : {current_raw[1]}",
            flush=True
        )

        print(
            f"   CR_raw      : {current_raw[2]}",
            flush=True
        )

        print(
            f"   BC_raw      : {current_raw[3]}",
            flush=True
        )

        print(
            f"   Uploaded    : 0",
            flush=True
        )

        print(
            f"   Timestamp   : {timestamp}",
            flush=True
        )

        return True

    except sqlite3.Error as e:

        conn.rollback()

        print(
            f"\n❌ Database insert failed: {e}",
            flush=True
        )

        return False


# ============================================================
# MAIN PRESSURE LOGIC
# ============================================================

def main():

    # --------------------------------------------------------
    # IMPORTANT INITIALIZATION
    # --------------------------------------------------------

    first_pressure_stored = False

    last_raw = None

    print()
    print("=" * 75)
    print("🚀 PRESSURE CAPTURE SYSTEM STARTED")
    print("=" * 75)

    print(
        f"📊 RAW_THRESHOLD = {RAW_THRESHOLD}",
        flush=True
    )

    print(
        f"⏱ READ_INTERVAL = {READ_INTERVAL} sec",
        flush=True
    )

    print("=" * 75)

    while True:

        # ====================================================
        # READ ADS1115
        # ====================================================

        current_raw = read_raw_values()

        if current_raw is None:

            print(
                "\n⚠️ ADS1115 reading unavailable",
                flush=True
            )

            time.sleep(1)

            continue


        timestamp = time.strftime(
            "%Y-%m-%d %H:%M:%S"
        )


        # ====================================================
        # FIRST PRESSURE READING
        # ====================================================

        if not first_pressure_stored:

            print(
                "\n📌 FIRST PRESSURE READING",
                flush=True
            )

            print(
                f"   BP_raw = {current_raw[0]}",
                flush=True
            )

            print(
                f"   FP_raw = {current_raw[1]}",
                flush=True
            )

            print(
                f"   CR_raw = {current_raw[2]}",
                flush=True
            )

            print(
                f"   BC_raw = {current_raw[3]}",
                flush=True
            )

            success = insert_pressure_record(
                current_raw,
                timestamp
            )

            if success:

                # IMPORTANT:
                # First stored pressure becomes reference.
                last_raw = current_raw

                first_pressure_stored = True

                print(
                    "\n✅ FIRST PRESSURE READING STORED",
                    flush=True
                )

                print(
                    f"   last_raw = {last_raw}",
                    flush=True
                )

            time.sleep(READ_INTERVAL)

            continue


        # ====================================================
        # PRESSURE DIFFERENCE CALCULATION
        # ====================================================

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


        # ====================================================
        # PRESSURE CHANGE DETECTED
        # ====================================================

        if (
            bp_diff >= RAW_THRESHOLD
            or
            fp_diff >= RAW_THRESHOLD
            or
            cr_diff >= RAW_THRESHOLD
            or
            bc_diff >= RAW_THRESHOLD
        ):

            print(
                "\n⚠️ PRESSURE CHANGE DETECTED",
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

            print(
                f"\n   Previous:"
                f" BP={last_raw[0]},"
                f" FP={last_raw[1]},"
                f" CR={last_raw[2]},"
                f" BC={last_raw[3]}",
                flush=True
            )

            print(
                f"   Current :"
                f" BP={current_raw[0]},"
                f" FP={current_raw[1]},"
                f" CR={current_raw[2]},"
                f" BC={current_raw[3]}",
                flush=True
            )


            # ------------------------------------------------
            # STORE ALL FOUR PRESSURE VALUES
            # ------------------------------------------------

            success = insert_pressure_record(
                current_raw,
                timestamp
            )


            # ------------------------------------------------
            # UPDATE REFERENCE ONLY AFTER SUCCESSFUL INSERT
            # ------------------------------------------------

            if success:

                last_raw = current_raw

                print(
                    "\n✅ last_raw UPDATED",
                    flush=True
                )

                print(
                    f"   BP={last_raw[0]},"
                    f" FP={last_raw[1]},"
                    f" CR={last_raw[2]},"
                    f" BC={last_raw[3]}",
                    flush=True
                )


        # ====================================================
        # NO SIGNIFICANT PRESSURE CHANGE
        # ====================================================

        else:

            # Do NOT update last_raw here.

            pass


        # ====================================================
        # NEXT READING
        # ====================================================

        time.sleep(READ_INTERVAL)


# ============================================================
# PROGRAM START
# ============================================================

if __name__ == "__main__":

    try:

        main()

    except KeyboardInterrupt:

        print(
            "\n\n🛑 Pressure capture stopped by user.",
            flush=True
        )

    except Exception as e:

        print(
            f"\n❌ Fatal error: {e}",
            flush=True
        )

    finally:

        try:
            conn.close()
        except Exception:
            pass

        print(
            "🔌 Database connection closed.",
            flush=True
        )