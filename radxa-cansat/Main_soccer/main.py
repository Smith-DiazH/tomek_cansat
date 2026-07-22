#!/usr/bin/env python3

from robot_state import RobotState
from uart        import STM32UART
from gps         import GPSReader
from lora        import LoRaTransceiver   # <-- pendiente tu código real
import queue
import time

PORT_STM32 = "/dev/ttyS7"
PORT_GPS   = "/dev/ttyS2"
PORT_LORA  = "/dev/ttyS4"
BAUD_STM32 = 115200
BAUD_GPS   = 9600
BAUD_LORA  = 115200

def main():
    log_q = queue.Queue()
    state = RobotState()

    uart = STM32UART(state, log_q, port=PORT_STM32, baud=BAUD_STM32)
    gps  = GPSReader(state, log_q, port=PORT_GPS, baud=BAUD_GPS)
    lora = LoRaTransceiver(state, log_q, port=PORT_LORA, baud=BAUD_LORA)

    uart.start()
    gps.start()
    lora.start()

    print("Sistema iniciado.")

    try:
        while True:
            # Log opcional en consola
            while not log_q.empty():
                print(log_q.get())
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nDeteniendo sistema...")
        uart.stop()
        gps.stop()
        lora.stop()

if __name__ == "__main__":
    main()
