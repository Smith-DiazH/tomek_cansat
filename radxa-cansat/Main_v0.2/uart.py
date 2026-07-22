 
#!/usr/bin/env python3
"""
uart.py  Comunicación binaria Radxa <-> STM32

RX (STM32 ? Radxa): [0xAA][0x55][yaw][pitch][roll][left_spd][right_spd][CRC16]
                      2 + 5×4 + 2 = 24 bytes

TX (Radxa ? STM32): [0xAA][0x55][VL][VR][CRC16]
                      2 + 2×4 + 2 = 12 bytes
"""
import serial
import struct
import threading
import time

HEADER         = b'\xAA\x55'
RX_N_FLOATS    = 5                          # yaw, pitch, roll, left_spd, right_spd
RX_PACKET_SIZE = 2 + RX_N_FLOATS * 4 + 2   # 24 bytes
TX_PACKET_SIZE = 2 + 2 * 4 + 2             # 12 bytes

# Frecuencia de transmisión (Radxa ? STM32)
# Independiente de la frecuencia a la que envíe la STM32
TX_HZ = 20
TX_PERIOD = 1.0 / TX_HZ


def crc16(data: bytes) -> int:
    """
    CRC-16/CCITT-FALSE  (poly=0x1021, init=0xFFFF, no reflejos).
    Debes usar el mismo algoritmo en la STM32.
    """
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = (crc << 1) ^ 0x1021 if crc & 0x8000 else crc << 1
            crc &= 0xFFFF
    return crc


class STM32UART:
    def __init__(self, port: str, baudrate: int, robot_state):
        self.state   = robot_state
        self._stop   = False
        self._tx_lock = threading.Lock()

        self._serial = serial.Serial(port, baudrate, timeout=0.1)

        # Hilo RX  escucha continuamente
        self._rx_thread = threading.Thread(
            target=self._rx_loop, name="UART-RX", daemon=True
        )
        self._rx_thread.start()

        # Hilo TX  transmite a TX_HZ
        self._tx_thread = threading.Thread(
            target=self._tx_loop, name="UART-TX", daemon=True
        )
        self._tx_thread.start()

        print(f"[UART] Abierto {port} @ {baudrate}  RX continuo, TX a {TX_HZ} Hz")

    # ------------------------------------------------------------------
    # RX
    # ------------------------------------------------------------------
    def _rx_loop(self):
        buf = b""
        crc_errors = 0

        while not self._stop:
            try:
                waiting = self._serial.in_waiting
                if waiting:
                    buf += self._serial.read(waiting)
                else:
                    time.sleep(0.002)   # ~2 ms de pausa si no hay datos
                    continue

                # Consumir todos los paquetes completos que haya en el buffer
                while True:
                    idx = buf.find(HEADER)
                    if idx == -1:
                        buf = b""
                        break
                    if idx > 0:
                        buf = buf[idx:]   # descartar basura previa al header

                    if len(buf) < RX_PACKET_SIZE:
                        break   # paquete incompleto  esperar más bytes

                    packet  = buf[:RX_PACKET_SIZE]
                    buf     = buf[RX_PACKET_SIZE:]

                    self._parse(packet, crc_errors)

            except Exception as e:
                print(f"[UART RX] Excepción: {e}")
                time.sleep(0.01)

    def _parse(self, packet: bytes, crc_errors: int):
        rx_crc   = struct.unpack_from('<H', packet, RX_PACKET_SIZE - 2)[0]
        calc_crc = crc16(packet[:RX_PACKET_SIZE - 2])

        if rx_crc != calc_crc:
            crc_errors += 1
            if crc_errors % 10 == 1:   # no spamear el log
                print(f"[UART RX] CRC error #{crc_errors}  "
                      f"recibido {rx_crc:#06x}, calculado {calc_crc:#06x}")
            return

        yaw, pitch, roll, left_spd, right_spd = struct.unpack_from('<5f', packet, 2)

        self.state.update_imu(yaw, pitch, roll)
        self.state.update_speeds(left_spd, right_spd)

    # ------------------------------------------------------------------
    # TX
    # ------------------------------------------------------------------
    def _tx_loop(self):
        while not self._stop:
            t0 = time.monotonic()

            vl, vr = self.state.get_motor_command()
            self._send(vl, vr)

            # Dormir el tiempo restante para mantener TX_HZ exacto
            elapsed = time.monotonic() - t0
            sleep_t = TX_PERIOD - elapsed
            if sleep_t > 0:
                time.sleep(sleep_t)

    def _send(self, vl: float, vr: float):
        payload = struct.pack('<2f', vl, vr)
        crc     = crc16(HEADER + payload)
        packet  = HEADER + payload + struct.pack('<H', crc)

        with self._tx_lock:
            try:
                self._serial.write(packet)
                self._serial.flush()
            except Exception as e:
                print(f"[UART TX] Error: {e}")

    # ------------------------------------------------------------------
    def stop(self):
        self._stop = True
        time.sleep(0.1)
        self._serial.close()
