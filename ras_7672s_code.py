
#!/usr/bin/env python3
import time
import pigpio

# Raspberry Pi 3A+
TX_GPIO = 4       # Physical pin 7 -> SIM7672S RXD
RX_GPIO = 5       # Physical pin 29 -> SIM7672S TXD
BAUDRATE = 9600   # Must match the modem UART baud rate

pi = pigpio.pi()

if not pi.connected:
    raise SystemExit(
        "Cannot connect to pigpio daemon. "
        "Start the daemon or check whether pigpio is supported."
    )

try:
    # Configure bit-banged serial receive on GPIO5
    pi.set_mode(RX_GPIO, pigpio.INPUT)
    pi.set_pull_up_down(RX_GPIO, pigpio.PUD_UP)

    # Open software UART receiver
    result = pi.bb_serial_read_open(
        RX_GPIO, BAUDRATE, 8
    )

    if result != 0:
        raise RuntimeError(
            f"Could not open software UART RX: {result}"
        )

    print("SIM7672S software UART AT test")
    print("TX GPIO4 / RX GPIO5 / baud:", BAUDRATE)
    print("Type AT, ATI, AT+CPIN?, AT+CSQ, or exit.")

    while True:
        command = input("AT> ").strip()

        if command.lower() == "exit":
            break

        if not command:
            continue

        # Transmit command on GPIO4
        pi.wave_clear()
        pi.wave_add_serial(
            TX_GPIO, BAUDRATE,
            command + "\r\n"
        )
        wave_id = pi.wave_create()

        if wave_id < 0:
            print("Could not create TX waveform.")
            continue

        pi.wave_send_once(wave_id)

        while pi.wave_tx_busy():
            time.sleep(0.01)

        pi.wave_delete(wave_id)

        # Collect response from GPIO5
        time.sleep(1)
        count, data = pi.bb_serial_read(RX_GPIO)

        if count:
            print(data.decode("utf-8", errors="replace"))
        else:
            print("No response. Check baud rate, wiring, "
                  "modem power and UART configuration.")

finally:
    try:
        pi.bb_serial_read_close(RX_GPIO)
    except Exception:
        pass

    pi.stop()
