import serial
import time

PORT = "/dev/ttyAMA3"
BAUD = 115200

print(f"Opening {PORT} at {BAUD} baud...")

try:
    ser = serial.Serial(
        port=PORT,
        baudrate=BAUD,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=2
    )

    time.sleep(1)
    ser.reset_input_buffer()
    ser.reset_output_buffer()

    commands = [
        "AT",
        "ATI",
        "AT+CPIN?",
        "AT+CSQ",
        "AT+CREG?"
    ]

    for cmd in commands:
        print(f"\n>>> {cmd}")
        ser.write((cmd + "\r\n").encode())
        time.sleep(1)

        response = ser.read_all().decode(
            "utf-8",
            errors="ignore"
        )

        print("<<<")
        print(response if response else "[NO RESPONSE]")

    ser.close()
    print("\nUART test completed.")

except Exception as e:
    print(f"\nUART ERROR: {e}")