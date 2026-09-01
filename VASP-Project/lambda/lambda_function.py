import os
import json
import pg8000
from datetime import datetime

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_DB = os.environ.get("SUPABASE_DB", "postgres")
SUPABASE_USER = os.environ.get("SUPABASE_USER", "postgres")
SUPABASE_PASSWORD = os.environ.get("SUPABASE_PASSWORD")
SUPABASE_PORT = int(os.environ.get("SUPABASE_PORT", 5432))

def lambda_handler(event, context):
    # Parse incoming event
    data = event if isinstance(event, dict) else json.loads(event)

    created_at = data.get("created_at", datetime.utcnow().isoformat())
    bp_pressure = data.get("bp_pressure", 0.0)
    fp_pressure = data.get("fp_pressure", 0.0)
    cr_pressure = data.get("cr_pressure", 0.0)
    bc_pressure = data.get("bc_pressure", 0.0)
    brake_fault = data.get("brake_fault", "none")
    brake_time = data.get("brake_time", datetime.utcnow().isoformat())
    event_trigger = data.get("event_trigger", "none")
    brake_status = data.get("brake_status", "idle")

    try:
        conn = pg8000.connect(
            host=SUPABASE_URL.replace("https://", ""),
            database=SUPABASE_DB,
            user=SUPABASE_USER,
            password=SUPABASE_PASSWORD,
            port=SUPABASE_PORT
        )
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO brake_data
            (created_at, bp_pressure, fp_pressure, cr_pressure, bc_pressure, brake_fault, brake_time, event_trigger, brake_status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (created_at, bp_pressure, fp_pressure, cr_pressure, bc_pressure,
              brake_fault, brake_time, event_trigger, brake_status))
        conn.commit()
        cursor.close()
        conn.close()
        return {"statusCode": 200, "body": json.dumps("Inserted into Supabase successfully!")}
    except Exception as e:
        return {"statusCode": 500, "body": str(e)}
