
#!/usr/bin/env python3
"""SIM7672S AT and GNSS diagnostic utility for Raspberry Pi."""

import sys
import time

import serial
from serial.tools import list_ports

BAUD_RATE = 115200
AT_TIMEOUT = 1.0

AT_COMMANDS = [
    ("ATI", 1.0),
    ("AT+CPIN?", 1.0),
    ("AT+CSQ", 1.0),
    ("AT+CREG?", 1.0),
    ("AT+CGREG?", 1.0),
    ("AT+CEREG?", 1.0),
    ("AT+CGATT?", 1.0),
    ("AT+CGNSSPWR=1", 2.0),
    ("AT+CGNSSPWR?", 1.0),
    ("AT+CGNSSINFO", 1.0),
    ("AT+CGPSINFO", 1.0),
]


def show_ports():
    ports = list(list_ports.comports())

    print("Detected serial ports:")
    if not ports:
        print("  None")
    for item in ports:
        print(f"  {item.device}: {item.description}")

    return ports


def send_at(modem, command, delay=AT_TIMEOUT):
    print(f"\n>>> {command}")
    modem.reset_input_buffer()
    modem.write((command + "\r\n").encode("ascii"))
    modem.flush()
    time.sleep(delay)

    response = modem.read_all().decode(
        "utf-8", errors="replace"
    ).strip()

    print(response if response else "(No response)")
    return response


def main():
    print("===== SIM7672S AT / GNSS DIAGNOSTIC =====")

    ports = show_ports()

    # Accept an explicitly specified serial device.
    port = sys.argv[1] if len(sys.argv) > 1 else None

    if port is None:
        candidates = [
            item.device
            for item in ports
            if item.device.startswith(
                ("/dev/ttyUSB", "/dev/ttyACM")
            )
        ]

        # Do not assume ttyS0 is connected to the modem.
        if candidates:
            port = candidates[0]

    if port is None:
        print("\nERROR: No USB serial device detected.")
        print("Your /dev/serial0 currently points to /dev/ttyS0.")
        print("GPIO4/GPIO5 are not a UART merely because they")
        print("are configured as GPIO inputs.")
        print("\nNo AT commands were sent.")
        print("Use a supported GPIO software-UART driver,")
        print("or a USB-to-UART adapter and rerun this script.")
        print("\nDo not change the port to /dev/ttyS0 unless")
        print("the modem is physically connected to that UART.")
        return 2

    try:
        with serial.Serial(
            port=port,
            baudrate=BAUD_RATE,
            timeout=0.2,
            write_timeout=2,
        ) as modem:
            time.sleep(0.5)

            response = send_at(modem, "AT")
            if "OK" not in response:
                print("\nERROR: Modem did not return OK to AT.")
                print("Check wiring, baud rate, modem power and logic levels.")
                return 1

            print("\nAT communication successful.")

            for command, delay in AT_COMMANDS:
                send_at(modem, command, delay)

            print("\n===== DIAGNOSTIC COMPLETE =====")
            print("GNSS may require an antenna and a clear outdoor view.")

    except (serial.SerialException, OSError) as exc:
        print(f"\nSERIAL ERROR: {exc}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
