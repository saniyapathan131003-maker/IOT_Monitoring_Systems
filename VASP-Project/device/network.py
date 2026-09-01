import sqlite3
import requests
import time
from datetime import datetime
import os

DB_NAME = "network_monitor.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    
    # Create table if it doesn't exist
    cur.execute('''
        CREATE TABLE IF NOT EXISTS network_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            response_time REAL,
            url TEXT
        )
    ''')
    
    columns = [col[1] for col in cur.execute("PRAGMA table_info(network_log)")]
    
    if "http_status" not in columns:
        cur.execute("ALTER TABLE network_log ADD COLUMN http_status INTEGER")
    if "content_length" not in columns:
        cur.execute("ALTER TABLE network_log ADD COLUMN content_length INTEGER")
    if "error_message" not in columns:
        cur.execute("ALTER TABLE network_log ADD COLUMN error_message TEXT")
    
    conn.commit()
    conn.close()

def check_network(url="https://www.cloudflare.com"):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    try:
        start = time.time()
        response = requests.get(url, timeout=5) 
        end = time.time()
        
        response_time = round(end - start, 2)
        http_status = response.status_code
        content_length = len(response.content)
        error_message = None  
    
    except requests.RequestException as e:
        response_time = None
        http_status = None
        content_length = None
        error_message = str(e)  # Store exception text
    
    # Insert record into database
    cur.execute('''
        INSERT INTO network_log (timestamp, response_time, url, http_status, content_length, error_message)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (timestamp, response_time, url, http_status, content_length, error_message))
    
    conn.commit()
    conn.close()
    
    # Print log
    if error_message:
        print(f"{timestamp} | URL: {url} | NETWORK FAILURE: {error_message}")
    else:
        print(f"{timestamp} | URL: {url} | HTTP Status: {http_status} | Response Time: {response_time}s | Content Length: {content_length} bytes")

CHECK_INTERVAL = 10  # seconds

if __name__ == "__main__":
    print("Initializing database...")
    init_db()
    print("Starting network monitoring...")
    
    while True:
        check_network()
        time.sleep(CHECK_INTERVAL)