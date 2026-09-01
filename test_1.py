# Raspberry Pi – ADS1115 4-Channel Pressure Data Logger

#python
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

# ADS1115 configuration
ADC_GAIN = 1

# 160-ohm shunt resistor for 4-20 mA
SHUNT_RESISTOR = 160.0

# Pressure transmitter configuration
CURRENT_MIN = 4.0      # mA
CURRENT_MAX = 20.0     # mA

PRESSURE_MIN = 0.0     # bar
PRESSURE_MAX = 10.0    # bar


# ============================================================
# CREATE DATABASE DIRECTORY
# ============================================================

os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


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

def save_reading(timestamp,
                 sensor,
                 adc_channel,
                 raw_value,
                 adc_voltage,
                 current_ma,
                 pressure_ideal):

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
# CURRENT CALCULATION
# ============================================================

def voltage_to_current(voltage):
    """
    Calculate 4-20 mA current using the 160 ohm shunt resistor.

    I = V / R

    Example:
    4 mA  -> 0.64 V
    20 mA -> 3.20 V
    """

    current_amp = voltage / SHUNT_RESISTOR

    current_ma = current_amp * 1000.0

    return current_ma


# ============================================================
# PRESSURE CALCULATION
# ============================================================

def current_to_pressure(current_ma):
    """
    Convert 4-20 mA transmitter output to pressure.

    4 mA  = 0 bar
    20 mA = 10 bar

    Linear conversion:

    Pressure =
        ((Current - 4) / 16) * 10
    """

    pressure = (
        (current_ma - CURRENT_MIN)
        / (CURRENT_MAX - CURRENT_MIN)
    ) * (PRESSURE_MAX - PRESSURE_MIN) + PRESSURE_MIN

    # Prevent small negative values caused by noise
    if pressure < PRESSURE_MIN:
        pressure = PRESSURE_MIN

    # Prevent values above maximum range
    if pressure > PRESSURE_MAX:
        pressure = PRESSURE_MAX

    return pressure


# ============================================================
# ADS1115 INITIALIZATION
# ============================================================

i2c = busio.I2C(
    board.SCL,
    board.SDA
)

ads = ADS1115(i2c)

ads.gain = ADC_GAIN


# ============================================================
# CHANNEL CONFIGURATION
# ============================================================

bp_channel = AnalogIn(
    ads,
    ADS1115.P0
)

fp_channel = AnalogIn(
    ads,
    ADS1115.P1
)

cr_channel = AnalogIn(
    ads,
    ADS1115.P2
)

bc_channel = AnalogIn(
    ads,
    ADS1115.P3
)


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


print("==============================================")
print(" ADS1115 4-Channel Pressure Data Logger")
print("==============================================")
print("A0 -> BP")
print("A1 -> FP")
print("A2 -> CR")
print("A3 -> BC")
print("----------------------------------------------")
print("Database:", DB_PATH)
print("----------------------------------------------")


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

            # ------------------------------------------------
            # READ RAW ADC VALUE
            # ------------------------------------------------

            raw_value = adc.value

            # ------------------------------------------------
            # READ ADC VOLTAGE
            # ------------------------------------------------

            adc_voltage = adc.voltage

            # ------------------------------------------------
            # CALCULATE CURRENT
            # ------------------------------------------------

            current_ma = voltage_to_current(
                adc_voltage
            )

            # ------------------------------------------------
            # CALCULATE PRESSURE
            # ------------------------------------------------

            pressure_ideal = current_to_pressure(
                current_ma
            )

            # ------------------------------------------------
            # SAVE TO DATABASE
            # ------------------------------------------------

            save_reading(
                timestamp=timestamp,
                sensor=sensor_name,
                adc_channel=adc_channel,
                raw_value=raw_value,
                adc_voltage=adc_voltage,
                current_ma=current_ma,
                pressure_ideal=pressure_ideal
            )

            # ------------------------------------------------
            # DISPLAY
            # ------------------------------------------------

            print(
                f"{timestamp} | "
                f"{sensor_name} | "
                f"{adc_channel} | "
                f"RAW={raw_value} | "
                f"V={adc_voltage:.4f} V | "
                f"I={current_ma:.3f} mA | "
                f"P={pressure_ideal:.3f} bar"
            )

        print("----------------------------------------------")

        # Reading interval
        time.sleep(1)


except KeyboardInterrupt:

    print("\nProgram stopped by user.")


except Exception as e:

    print("\nERROR:", e)
```
