
#!/usr/bin/env python3
import time
import serial

# USB-to-TTL adapter serial port.
# Change this if your adapter uses another port.
PORT = "/dev/ttyUSB0"
BAUDRATE = 115200


def send_at(ser, command, wait=2):
    """Send an AT command and collect its response."""
    print(f"\n>>> {command}")

    ser.reset_input_buffer()
    ser.write((command + "\r\n").encode("ascii"))
    ser.flush()

    time.sleep(wait)
    response = ser.read_all().decode(
        "utf-8", errors="replace"
    ).strip()

    print(response if response else "No response")
    return response


def main():
    try:
        with serial.Serial(
            PORT,
            BAUDRATE,
            timeout=0.5,
            write_timeout=2
        ) as ser:

            time.sleep(2)
            ser.reset_input_buffer()

            print("SIM7672S AT / GPS / GNSS TEST")
            print("Serial port:", PORT)
            print("Baud rate:", BAUDRATE)

            # Basic modem and SIM tests
            send_at(ser, "AT")
            send_at(ser, "ATE0")
            send_at(ser, "ATI")
            send_at(ser, "AT+CPIN?")
            send_at(ser, "AT+CSQ")
            send_at(ser, "AT+CREG?")
            send_at(ser, "AT+CEREG?")
            send_at(ser, "AT+CGATT?")

            # GNSS capability check and power on
            send_at(ser, "AT+CGNSSPWR?")
            send_at(ser, "AT+CGNSSPWR=1", wait=3)

            print("\nWaiting for GNSS location.")
            print("Place the antenna outdoors with a clear sky view.")
            print("A first fix may take several minutes.")

            # Allow time for the receiver to acquire satellites.
            for attempt in range(1, 31):
                print(f"\n--- GNSS check {attempt}/30 ---")

                info = send_at(
                    ser, "AT+CGNSSINFO", wait=2
                )

                gps = send_at(
                    ser, "AT+CGPSINFO", wait=1
                )

                if (
                    info and
                    "+CGNSSINFO:" in info and
                    "+CGNSSINFO: ," not in info
                ):
                    print("GNSS information received.")

                if (
                    gps and
                    "+CGPSINFO:" in gps and
                    "+CGPSINFO: ," not in gps
                ):
                    print("GPS information received.")

                time.sleep(3)

            print("\nTest finished.")
            print("Check responses above for AT OK and valid coordinates.")

    except serial.SerialException as exc:
        print("Serial error:", exc)
        print("Check the port, cable, permissions and wiring.")

    except KeyboardInterrupt:
        print("\nTest stopped by user.")


if __name__ == "__main__":
    main()
