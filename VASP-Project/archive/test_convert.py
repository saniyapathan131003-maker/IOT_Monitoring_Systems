import time
import board
import busio
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn

# Initialize I2C
i2c = busio.I2C(board.SCL, board.SDA)

# Initialize ADS1115
ads = ADS.ADS1115(i2c)
ads.gain = 1  # Adjust gain if needed

# Create single-ended channels
chan0 = AnalogIn(ads, 0)
chan1 = AnalogIn(ads, 1)
chan2 = AnalogIn(ads, 2)
chan3 = AnalogIn(ads, 3)

def voltage_to_pressure(voltage):
    # Example conversion formula
    # Adjust scale based on your sensor datasheet
    return (voltage / 5.0) * 10  # bar

while True:
    raw_values = [chan0.value, chan1.value, chan2.value, chan3.value]
    voltages = [chan0.voltage, chan1.voltage, chan2.voltage, chan3.voltage]
    pressures = [voltage_to_pressure(v) for v in voltages]

    print("RAW VALUES:", raw_values)
    print("VOLTAGES:", [f"{v:.3f} V" for v in voltages])
    print("PRESSURE:", [f"{p:.2f} bar" for p in pressures])
    print("-" * 40)
    time.sleep(2)
