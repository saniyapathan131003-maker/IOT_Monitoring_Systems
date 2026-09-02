import serial
import time

PORT = "/dev/serial0"
BAUDRATE = 115200

try:
    ser = serial.Serial(
        port=PORT,
        baudrate=BAUDRATE,
        timeout=2
    )

    print("===================================")
    print("   EC200U UART CONNECTION TEST")
    print("===================================")
    print(f"Port : {PORT}")
    print(f"Baud : {BAUDRATE}")
    print("Sending AT command...\n")

    time.sleep(1)

    # Clear old data
    ser.reset_input_buffer()

    # Send AT
    ser.write(b"AT\r\n")
    time.sleep(1)

    response = ser.read_all().decode(errors="ignore")

    print("EC200U Response:")
    print("----------------")
    print(response)

    if "OK" in response:
        print("\n✅ EC200U UART CONNECTION SUCCESSFUL")

        # Get module information
        print("\nChecking module information...")
        ser.write(b"ATI\r\n")
        time.sleep(1)

        response = ser.read_all().decode(errors="ignore")
        print(response)

    else:
        print("\n❌ No valid response from EC200U")
        print("Check:")
        print("1. EC200U power supply")
        print("2. TX/RX wiring")
        print("3. GND connection")
        print("4. Baud rate")

    ser.close()

except Exception as e:
    print(f"\n❌ UART ERROR: {e}")