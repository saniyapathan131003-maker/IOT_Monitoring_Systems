cat > test_sim7672s.py <<'PY'
#!/usr/bin/env python3
import time
import serial

PORT = "/dev/ttyUSB0"
BAUD = 115200

try:
    with serial.Serial(PORT, BAUD, timeout=2) as modem:
        time.sleep(1)
        modem.reset_input_buffer()
        modem.write(b"AT\r\n")
        modem.flush()

        response = modem.read_until(b"\n").decode(
            "utf-8", errors="replace"
        ).strip()

        print("AT response:", repr(response))

        if "OK" in response:
            print("RESULT: MODEM RESPONDING")
        else:
            print("RESULT: NO VALID AT RESPONSE")

except Exception as error:
    print("RESULT: SERIAL TEST FAILED")
    print("Reason:", error)
PY