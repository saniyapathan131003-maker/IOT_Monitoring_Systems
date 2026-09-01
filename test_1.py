# ============================================================
# Raspberry Pi – ADS1115 4-Channel Pressure Data Logger
# ============================================================

import os
import time
import sqlite3
from datetime import datetime

import board
import busio
from adafruit_ads1x15.ads1115 import ADS1115
from adafruit_ads1x15.analog_in import AnalogIn


# ============================================================
# CONFIGURATION
# ============================================================

DB_PATH = "db/test1_db.db"

# ADS1115 I2C address
# Raspberry Pi detected both 0x48 and 0x49.
# Change to 0x49 if your required ADS1115 is at 0x49.
ADS1115_ADDRESS = 0x48

# ADS1115 gain
ADC_GAIN = 1

# 160-ohm shunt resistor for 4-20 mA
SHUNT_RESISTOR = 160.0

# Pressure transmitter
CURRENT_MIN = 4.0       # mA
CURRENT_MAX = 20.0      # mA

PRESSURE_MIN = 0.0      # bar
PRESSURE_MAX = 10.0     # bar


# ============================================================
# CREATE DATABASE DIRECTORY
# ============================================================

db_directory = os.path.dirname(DB_PATH)

if db_directory:
    os.makedirs(db_directory, exist_ok=True)


# ============================================================
# DATABASE INITIALIZATION
# ============================================================

def init_database():

    conn = sqlite3.connect(DB_PATH)

    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pressure_readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            sensor TEXT NOT NULL,
            adc_channel TEXT NOT NULL,
            raw_value INTEGER NOT NULL,
            adc_voltage REAL NOT NULL,
            current_ma REAL NOT NULL,
            pressure_ideal REAL NOT NULL
        )
    """)

    conn.commit()
    conn.close()


# ============================================================
# SAVE READING TO DATABASE
# ============================================================

def save_reading(
    timestamp,
    sensor,
    adc_channel,
    raw_value,
    adc_voltage,
    current_ma,
    pressure_ideal
):

    conn = sqlite3.connect(DB_PATH)

    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO pressure_readings (
            timestamp,
            sensor,
            adc_channel,
            raw_value,
            adc_voltage,
            current_ma,
            pressure_ideal
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        timestamp,
        sensor,
        adc_channel,
        raw_value,
        adc_voltage,
        current_ma,
        pressure_ideal
    ))

    conn.commit()
    conn.close()


# ============================================================
# VOLTAGE → CURRENT
# ============================================================

def voltage_to_current(voltage):
    """
    Convert shunt voltage to current.

    I = V / R

    160 ohm shunt:

    4 mA  = 0.64 V
    20 mA = 3.20 V
    """

    current_amp = voltage / SHUNT_RESISTOR

    current_ma = current_amp * 1000.0

    return current_ma


# ============================================================
# CURRENT → PRESSURE
# ============================================================

def current_to_pressure(current_ma):
    """
    Convert 4-20 mA to 0-10 bar.

    4 mA  = 0 bar
    20 mA = 10 bar
    """

    pressure = (
        (current_ma - CURRENT_MIN)
        / (CURRENT_MAX - CURRENT_MIN)
    ) * (PRESSURE_MAX - PRESSURE_MIN) + PRESSURE_MIN

    # Limit pressure to configured range
    pressure = max(PRESSURE_MIN, pressure)
    pressure = min(PRESSURE_MAX, pressure)

    return pressure


# ============================================================
# ADS1115 INITIALIZATION
# ============================================================

print("Initializing I2C...")

i2c = busio.I2C(
    board.SCL,
    board.SDA
)


# ============================================================
# ADS1115
# ============================================================

print(
    f"Initializing ADS1115 at address "
    f"0x{ADS1115_ADDRESS:02X}..."
)

ads = ADS1115(
    i2c,
    address=ADS1115_ADDRESS
)

ads.gain = ADC_GAIN


print("ADS1115 initialized successfully.")


# ============================================================
# CHANNEL CONFIGURATION
# ============================================================

# IMPORTANT:
# Do NOT use ADS1115.P0 / ADS1115.P1.
#
# Correct:
# AnalogIn(ads, 0)
# AnalogIn(ads, 1)
# AnalogIn(ads, 2)
# AnalogIn(ads, 3)

bp_channel = AnalogIn(
    ads,
    0
)

fp_channel = AnalogIn(
    ads,
    1
)

cr_channel = AnalogIn(
    ads,
    2
)

bc_channel = AnalogIn(
    ads,
    3
)


# ============================================================
# SENSOR CONFIGURATION
# ============================================================

channels = {

    "BP": {
        "channel": "A0",
        "adc": bp_channel
    },

    "FP": {
        "channel": "A1",
        "adc": fp_channel
    },

    "CR": {
        "channel": "A2",
        "adc": cr_channel
    },

    "BC": {
        "channel": "A3",
        "adc": bc_channel
    }
}


# ============================================================
# INITIALIZE DATABASE
# ============================================================

init_database()


# ============================================================
# START MESSAGE
# ============================================================

print()
print("==============================================")
print(" ADS1115 4-Channel Pressure Data Logger")
print("==============================================")
print(f"ADS1115 Address : 0x{ADS1115_ADDRESS:02X}")
print(f"ADC Gain        : {ADC_GAIN}")
print(f"Shunt Resistor  : {SHUNT_RESISTOR} ohm")
print("----------------------------------------------")
print("A0 -> BP")
print("A1 -> FP")
print("A2 -> CR")
print("A3 -> BC")
print("----------------------------------------------")
print("Database:", DB_PATH)
print("----------------------------------------------")
print("4 mA  -> 0.64 V -> 0 bar")
print("20 mA -> 3.20 V -> 10 bar")
print("----------------------------------------------")
print("Logging started...")
print()


# ============================================================
# MAIN LOOP
# ============================================================

try:

    while True:

        timestamp = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S.%f"
        )[:-3]

        for sensor_name, sensor_data in channels.items():

            adc_channel = sensor_data["channel"]
            adc = sensor_data["adc"]

            try:

                # --------------------------------------------
                # READ RAW ADC VALUE
                # --------------------------------------------

                raw_value = adc.value

                # --------------------------------------------
                # READ ADC VOLTAGE
                # --------------------------------------------

                adc_voltage = adc.voltage

                # --------------------------------------------
                # VOLTAGE → CURRENT
                # --------------------------------------------

                current_ma = voltage_to_current(
                    adc_voltage
                )

                # --------------------------------------------
                # CURRENT → PRESSURE
                # --------------------------------------------

                pressure_ideal = current_to_pressure(
                    current_ma
                )

                # --------------------------------------------
                # SAVE TO DATABASE
                # --------------------------------------------

                save_reading(
                    timestamp=timestamp,
                    sensor=sensor_name,
                    adc_channel=adc_channel,
                    raw_value=raw_value,
                    adc_voltage=adc_voltage,
                    current_ma=current_ma,
                    pressure_ideal=pressure_ideal
                )

                # --------------------------------------------
                # DISPLAY
                # --------------------------------------------

                print(
                    f"{timestamp} | "
                    f"{sensor_name:<3} | "
                    f"{adc_channel} | "
                    f"RAW={raw_value:6d} | "
                    f"V={adc_voltage:.4f} V | "
                    f"I={current_ma:.3f} mA | "
                    f"P={pressure_ideal:.3f} bar"
                )

            except Exception as channel_error:

                print(
                    f"{timestamp} | "
                    f"{sensor_name} | "
                    f"{adc_channel} | "
                    f"ERROR: {channel_error}"
                )

        print("----------------------------------------------")

        # Read every 1 second
        time.sleep(1)


# ============================================================
# STOP PROGRAM
# ============================================================

except KeyboardInterrupt:

    print()
    print("Program stopped by user.")


except Exception as e:

    print()
    print("FATAL ERROR:", e)