import serial
import time

PORT = "/dev/ttyAMA3"
BAUDRATE = 115200

try:
    ser = serial.Serial(PORT, BAUDRATE, timeout=2)

    print("UART3 opened successfully")

    ser.write(b"AT\r\n")
    time.sleep(1)

    response = ser.read_all()

    print("EC200U response:")
    print(response.decode(errors="replace"))

    ser.close()

except Exception as e:
    print("UART error:", e)