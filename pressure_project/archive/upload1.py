import sqlite3
import time

# Path to database
time.sleep(10)  # initial delay to allow other processes to start
DB_PATH = "project.db"  # database will be in the same folder as thee.py

def upload_status():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Fetch the oldest row not uploaded
    cursor.execute("SELECT * FROM brake_pressure_log WHERE uploaded=0 ORDER BY created_at LIMIT 1")
    row = cursor.fetchone()

    if row:
        # row = id, bp, fp, cr, bc, created_at, uploaded
        print(
            f"Uploading -> ID:{row[0]} | BP:{row[1]} | FP:{row[2]} | CR:{row[3]} | BC:{row[4]} | "
            f"Time:{row[5]} | Uploaded:{row[6]}",
            flush=True
        )

        # Mark as uploaded
        cursor.execute("UPDATE brake_pressure_log SET uploaded=1 WHERE id=?", (row[0],))
        conn.commit()
    else:
        print("No data to upload", flush=True)

    conn.close()

# Keep the uploader running continuously
if __name__ == "__main__":
    while True:
        upload_status()
        time.sleep(10)  # wait 10 seconds before checking again