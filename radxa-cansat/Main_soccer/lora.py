#!/usr/bin/env python3
"""
lora.py  Transceptor LoRa P2P bidireccional.

RX (base ? Radxa): comando de dirección de una sola letra
    Ejemplo: "F", "B", "L", "R", "G", "I", "H", "J", "S"

TX (Radxa ? base): telemetría del estado del rover
    Formato: "TEL,<lat>,<lon>,<alt>,<roll>,<pitch>,<yaw>,<fix>"
"""
import serial
import threading
import binascii
import time

LORA_PORT   = "/dev/ttyS4"
LORA_BAUD   = 115200
LORA_P2P    = "915000000:7:0:0:8:22"
LORA_TX_HZ  = 1

VALID_COMMANDS = {'F', 'B', 'L', 'R', 'G', 'I', 'H', 'J', 'S'}


class LoRaTransceiver(threading.Thread):
    def __init__(self, robot_state, log_q=None,
                 port=LORA_PORT, baud=LORA_BAUD,
                 p2p=LORA_P2P, tx_hz=LORA_TX_HZ):
        super().__init__(daemon=True, name="LoRa-Transceiver")
        self.state   = robot_state
        self.log_q   = log_q
        self.port    = port
        self.baud    = baud
        self.p2p     = p2p
        self.tx_period = 1.0 / tx_hz
        self._stop   = False
        self.ser     = None

    def stop(self):
        self._stop = True

    # ------------------------------------------------------------------
    # Helpers AT
    # ------------------------------------------------------------------
    def _at(self, cmd: str, wait: float = 0.1) -> str:
        if not (self.ser and self.ser.is_open):
            return ""
        self.ser.write((cmd + "\r\n").encode())
        self.ser.flush()
        time.sleep(wait)
        resp = self.ser.read(self.ser.in_waiting or 1).decode(errors="ignore").strip()
        return resp

    def _rearm_rx(self):
        self._at("AT+PRECV=0",     wait=0.05)
        self._at("AT+PRECV=65535", wait=0.05)

    def _send_text(self, text: str):
        self._at("AT+PRECV=0", wait=0.05)
        hexpl = binascii.hexlify(text.encode()).decode()
        self._at(f"AT+PSEND={hexpl}", wait=0.25)
        self._rearm_rx()

    # ------------------------------------------------------------------
    # Parser de comandos entrantes
    # ------------------------------------------------------------------
    def _handle_rx(self, payload: str):
        """
        Interpreta el payload recibido desde la base.
        Espera una sola letra: F, B, L, R, G, I, H, J, S
        """
        cmd = payload.strip().upper()

        if self.log_q:
            self.log_q.put(f"LORA_RX: {cmd}")

        if cmd in VALID_COMMANDS:
            self.state.set_command(cmd)
            print(f"[LoRa RX] Comando aplicado: {cmd}")
        else:
            print(f"[LoRa RX] Comando desconocido: {cmd}")

    # ------------------------------------------------------------------
    # Armar paquete de telemetría
    # ------------------------------------------------------------------
    def _build_telemetry(self) -> str:
        s = self.state.snapshot()
        fix = 1 if s["gps_fix"] else 0
        return (
            f"TEL,"
            f"{s['lat']:.6f},"
            f"{s['lon']:.6f},"
            f"{s['alt']:.1f},"
            f"{s['roll']:.1f},"
            f"{s['pitch']:.1f},"
            f"{s['yaw']:.1f},"
            f"{fix}"
        )

    # ------------------------------------------------------------------
    # Bucle principal
    # ------------------------------------------------------------------
    def run(self):
        try:
            self.ser = serial.Serial(self.port, self.baud, timeout=0.01)
            resp = self._at("AT", wait=0.1)
            if "OK" not in resp:
                print(f"[LoRa] Módulo no responde en {self.port}")
                return
            self._at("AT+NWM=0")
            self._at(f"AT+P2P={self.p2p}")
            self._rearm_rx()
            print(f"[LoRa] Listo en {self.port} | P2P={self.p2p} | TX={1/self.tx_period:.0f} Hz")
        except Exception as e:
            print(f"[LoRa] Error de inicialización: {e}")
            return

        buf     = ""
        last_tx = 0.0

        while not self._stop:
            try:
                t_end = time.monotonic() + 0.1
                while time.monotonic() < t_end:
                    if self.ser.in_waiting:
                        buf += self.ser.read(self.ser.in_waiting).decode(errors="ignore")

                    while "\n" in buf:
                        line, buf = buf.split("\n", 1)
                        line = line.strip()
                        if not line:
                            continue

                        if "+EVT:RXP2P:" in line:
                            hexpl = line.split(":")[-1]
                            try:
                                payload = binascii.unhexlify(hexpl).decode("utf-8", errors="ignore")
                                self._handle_rx(payload)
                            except Exception:
                                pass
                            self._rearm_rx()

                        elif "BUSY" in line or "P2P_RX_ON" in line:
                            self._rearm_rx()

                    time.sleep(0.01)

                if time.monotonic() - last_tx >= self.tx_period:
                    telemetry = self._build_telemetry()
                    self._send_text(telemetry)
                    last_tx = time.monotonic()
                    print(f"[LoRa TX] {telemetry}")
                    if self.log_q:
                        self.log_q.put(f"LORA_TX: {telemetry}")

            except Exception as e:
                print(f"[LoRa] Error en ciclo: {e}")
                time.sleep(0.5)

        self.ser.close()
