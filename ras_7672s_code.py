
#!/usr/bin/env python3
import sys
import time
import serial
from serial.tools import list_ports

BAUD_RATE = 115200


def send_at(modem, command, wait=1.0):
    print(f"\n>>> {command}")
    modem.reset_input_buffer()
    modem.write((command + "\r\n").encode("ascii"))
    modem.flush()
    time.sleep(wait)

    response = modem.read_all().decode("utf-8", errors="replace").strip()
    print(response if response else "(No response)")
    return response


def main():
    print("===== SIM7672S AT / GNSS TEST =====")

    ports = [p.device for p in list_ports.comports()]
    print("Detected ports:", ports if ports else "None")

    if len(sys.argv) > 1:
        port = sys.argv[1]
    else:
        port = next(
            (p for p in ports if p.startswith(("/dev/ttyUSB", "/dev/ttyACM"))),
            None,
        )

    if port is None:
        print("\nERROR: No USB serial port detected.")
        print("pySerial cannot use GPIO4/GPIO5 directly.")
        print("A supported software UART or USB-to-UART adapter is required.")
        return

    try:
        with serial.Serial(port, BAUD_RATE, timeout=0.3) as modem:
            time.sleep(1)

            response = send_at(modem, "AT")
            print("\nAT TEST:", "PASS" if "OK" in response else "NO RESPONSE")

            for command in (
                "ATI",
                "AT+CPIN?",
                "AT+CSQ",
                "AT+CREG?",
                "AT+CGREG?",
                "AT+CEREG?",
                "AT+CGATT?",
                "AT+CGNSSPWR=1",
                "AT+CGNSSPWR?",
                "AT+CGNSSINFO",
                "AT+CGPSINFO",
            ):
                send_at(modem, command, wait=2 if command == "AT+CGNSSPWR=1" else 1)

            print("\n===== TEST COMPLETE =====")
            print("GNSS may require an antenna and an outdoor satellite fix.")

    except serial.SerialException as error:
        print("Serial error:", error)


if __name__ == "__main__":
    main()
