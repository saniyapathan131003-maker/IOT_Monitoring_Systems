
#!/usr/bin/env python3
"""SIM7672S AT and GNSS diagnostic for Raspberry Pi."""

import argparse
import time

import serial


def send_at(modem, command, delay=1.0):
    print(f"\n>>> {command}")
    modem.reset_input_buffer()
    modem.write((command + "\r\n").encode("ascii"))
    modem.flush()
    time.sleep(delay)

    response = modem.read_all().decode("utf-8", errors="replace").strip()
    print(response or "(No response)")
    return response


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--port",
        required=True,
        help="Serial device exposed by your UART driver",
    )
    parser.add_argument("--baud", type=int, default=115200)
    args = parser.parse_args()

    try:
        with serial.Serial(
            args.port,
            args.baud,
            timeout=0.3,
            write_timeout=2,
        ) as modem:
            time.sleep(0.5)

            response = send_at(modem, "AT")
            if "OK" not in response:
                print("\nERROR: No AT response. Check wiring, baud rate,")
                print("modem power, UART voltage levels and driver.")
                return 1

            print("\nAT communication successful.")

            commands = [
                ("ATI", 1),
                ("AT+CPIN?", 1),
                ("AT+CSQ", 1),
                ("AT+CEREG?", 1),
                ("AT+CGATT?", 1),
                ("AT+CGNSSPWR=1", 2),
                ("AT+CGNSSPWR?", 1),
                ("AT+CGNSSINFO", 1),
                ("AT+CGPSINFO", 1),
            ]

            for command, delay in commands:
                send_at(modem, command, delay)

            print("\nDiagnostic complete.")
            print("GNSS may need a compatible antenna and outdoor sky view.")

    except (serial.SerialException, OSError) as exc:
        print(f"Serial error: {exc}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
