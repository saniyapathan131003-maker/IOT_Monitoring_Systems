import sqlite3
import time

DB_PATH = "C:/SQL_db/project.db"

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

def upload_to_app(row):
    print(f"Uploading -> ID:{row['id']} Time:{row['created_at']}")
    time.sleep(1)
    return True

while True:
    cur.execute("""
        SELECT * FROM brake_pressure_log
        WHERE uploaded = 0
        ORDER BY created_at ASC
        LIMIT 1
    """)
    row = cur.fetchone()

    if  row:
        if upload_to_app(row):
            cur.execute(
                "UPDATE brake_pressure_log SET uploaded = 1 WHERE id = ?",
                (row['id'],)
            )
            conn.commit()
            print(f"Row {row['id']} marked uploaded (0)")
    else:
        print("No data to upload")

    time.sleep(2)