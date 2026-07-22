#!/usr/bin/env python3
"""
test_uart.py  Validación aislada de uart.py (sin LoRa, sin GPS).

Prueba:
  1. Que los comandos de motor lleguen bien al STM32 (con rampa).
  2. Que la telemetría del IMU se reciba y se refleje en robot_state.
  3. Que el fail-safe funcione (deja de teclear y espera 2s).

TECLAS:
  w=F  s=B  a=L  d=R  q=G  e=I  z=H  c=J  ESPACIO/x=S
  i = imprime snapshot completo del robot_state (IMU)
  Ctrl+C = salir (manda STOP antes de cerrar)
"""
import sys
import time
import queue
import termios
import tty
import threading

from robot_state import RobotState
from uart import STM32UART

PORT_STM32 = "/dev/ttyS7"
BAUD_STM32 = 115200

KEYMAP = {
    'w': 'F', 's': 'B', 'a': 'L', 'd': 'R',
    'q': 'G', 'e': 'I', 'z': 'H', 'c': 'J',
    ' ': 'S', 'x': 'S',
}


def read_key():
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
    return ch


def print_logs(log_q):
    while True:
        try:
            msg = log_q.get(timeout=0.5)
            print(f"\r[LOG] {msg}")
        except queue.Empty:
            continue


def main():
    log_q = queue.Queue()
    state = RobotState()

    # timeout_cmd bajo (2s) a propósito para que veas el fail-safe actuar rápido
    uart = STM32UART(state, log_q, port=PORT_STM32, baud=BAUD_STM32, timeout_cmd=2.0)
    uart.start()

    threading.Thread(target=print_logs, args=(log_q,), daemon=True).start()

    print("\n=== TEST UART  Motores + IMU (sin LoRa/GPS) ===")
    print(" w/s: adelante/atrás   a/d: izq/der")
    print(" q/e: diag. adelante   z/c: diag. atrás")
    print(" ESPACIO o x: STOP     i: ver estado IMU actual")
    print(" Ctrl+C: salir\n")
    print("Prueba también: deja de teclear 3s y observa el FAIL-SAFE en el log.\n")

    try:
        while True:
            ch = read_key().lower()

            if ch == '\x03':  # Ctrl+C en modo raw
                break

            if ch == 'i':
                s = state.snapshot()
                print(f"\r[IMU] Roll={s['roll']:.2f}  Pitch={s['pitch']:.2f}  "
                      f"Yaw={s['yaw']:.2f}  | comando={s['command']}     ")
                continue

            if ch in KEYMAP:
                state.set_command(KEYMAP[ch])
                print(f"\r>> Comando enviado: {KEYMAP[ch]}     ", end="", flush=True)

    except KeyboardInterrupt:
        pass
    finally:
        print("\nDeteniendo: enviando STOP...")
        state.set_command('S')
        time.sleep(0.6)   # deja que la rampa baje y se mande el último 's'
        uart.stop()
        time.sleep(0.2)


if __name__ == "__main__":
    main() 
