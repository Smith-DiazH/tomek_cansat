#!/usr/bin/env python3
"""
=============================================================================
SENDER MULTIPLEXOR (GPS + STM32)  Radxa CM4
=============================================================================
Este script orquesta múltiples fuentes de datos, las formatea bajo un
protocolo pseudo-JSON y las encola para su transmisión vía LoRa P2P.

ARQUITECTURA DE PUERTOS:
------------------------
- /dev/ttyS4 (UART4): Módulo LoRa RAK3172 (115200 baudios)
- /dev/ttyS2 (UART2): Módulo GPS NMEA      (9600 baudios)
- /dev/ttyS7 (UART7): Microcontrolador STM32 (115200 baudios) -> uart7_m0

PROTOCOLOS ACEPTADOS EN COLA (Pseudo-JSON):
-------------------------------------------
  G,lat,lon,alt    -> Generado internamente por el hilo GPS
  A,x,y,z          -> Recibido crudo desde el STM32
  Y,x,y,z          -> Recibido crudo desde el STM32
  M,x,y,z          -> Recibido crudo desde el STM32
=============================================================================
"""
import time
import queue
import threading
import binascii
import serial

# ---------------------------------------------------------------
#  1. Hilo LoRa P2P Sender (El Embudo de Salida)
# ---------------------------------------------------------------
class LoRaP2PSender(threading.Thread):
    def __init__(self, q, port="/dev/ttyS4", baud=115200,
                 p2p="915000000:7:0:0:8:22", period=1.0):
        super().__init__(daemon=True)
        self.q, self.port, self.baud = q, port, baud
        self.p2p, self.period = p2p, period
        self._desconectar = False
        self.ser   = None

    def solicitar_parada(self):
        self._desconectar = True

    def _at(self, cmd, wait=0.25):
        if self.ser and self.ser.is_open:
            self.ser.write((cmd + "\r\n").encode())
            self.ser.flush()
            time.sleep(wait)

            # Leer la respuesta del chip
            respuesta = self.ser.read(self.ser.in_waiting or 1).decode(errors="ignore").strip()

            if respuesta:
                # Si responde un error del firmware
                if "ERROR" in respuesta or "BUSY" in respuesta:
                    print(f"?? [MÓDEM RAK - ALERTA]: Comando '{cmd}' devolvió error:\n{respuesta}")
                return respuesta
            else:
                # ¡SILENCIO TOTAL! El cable se soltó o el módulo se apagó
                print(f"?? [CRÍTICO - HARDWARE]: ¡EL MÓDULO LORA NO RESPONDE! Al enviar: '{cmd}'")
                print("   ?? Revisa la alimentación del RAK3172 y los pines TX/RX.")
                return ""

    def _send(self, text):
        self._at(f"AT+PSEND={binascii.hexlify(text.encode()).decode()}", wait=0.3)

    def run(self):
        try:
            self.ser = serial.Serial(self.port, self.baud, timeout=0.5) # Aumentamos un poco el timeout de chequeo

            # Probar si el módulo está vivo
            self.ser.write(b"AT\r\n")
            time.sleep(0.1)
            res = self.ser.read(self.ser.in_waiting).decode()

            if "OK" not in res:
                print(f"? [FALLO DE INICIALIZACIÓN]: Módulo LoRa no detectado en {self.port}. Abortando hilo.")
                return # Termina el hilo de ejecución de LoRa

            # Si pasa la prueba, continúa la configuración normal...
            self._at("AT+NWM=0")
            self._at(f"AT+P2P={self.p2p}")
            self._at("AT+PRECV=0")
            print(f"[LoRa] Antena TX lista y verificada en {self.port}")
        except Exception as e:
            print(f"[LoRa] Error Fatal: {e}"); return

        last = 0.0
        while not self._desconectar:
            try:
                payload = None
                try:
                    payload = self.q.get(timeout=self.period)
                except queue.Empty:
                    pass

                if payload:
                    dt = time.time() - last
                    # Limitar la tasa de transmisión para no saturar el chip LoRa
                    if dt < self.period:
                        time.sleep(self.period - dt)
                    self._send(payload.strip())
                    last = time.time()
                    print(f"?? [TX LORA] {payload.strip()}")
            except Exception as e:
                print(f"[LoRa] Error envío: {e}")
                time.sleep(0.5)

        if self.ser and self.ser.is_open:
            self.ser.close()

# ---------------------------------------------------------------
#  2. Hilo STM32 (Lector del IMU A/Y/M)
# ---------------------------------------------------------------
class STM32Reader(threading.Thread):
    def __init__(self, tx_queue, port="/dev/ttyS7", baud=115200):
        super().__init__(daemon=True)
        self.port, self.baud = port, baud
        self.tx_queue = tx_queue
        self._desconectar = False
        self.ser = None

    def solicitar_parada(self):
        self._desconectar = True

    def run(self):
        try:
            self.ser = serial.Serial(self.port, self.baud, timeout=1)
            print(f"[STM32] Escuchando IMU en {self.port} (uart7_m0)")
        except Exception as e:
            print(f"[STM32] Error abriendo puerto: {e}"); return

        buf = ""
        while not self._desconectar:
            try:
                if self.ser and self.ser.is_open:
                    buf += self.ser.read(256).decode(errors="ignore")
                    while "\n" in buf:
                        line, buf = buf.split("\n", 1)
                        line = line.strip()

                        # Validar que el STM32 envió un formato aceptado
                        if line.startswith(("A,", "Y,", "M,")):
                            # Enviar directamente a la cola de transmisión LoRa
                            self.tx_queue.put(line)
            except Exception as e:
                print(f"[STM32] Error lectura: {e}")
                time.sleep(0.5)

        if self.ser and self.ser.is_open:
            self.ser.close()

# ---------------------------------------------------------------
#  3. Hilo GPS (Generador de Prefijo G)
# ---------------------------------------------------------------
class GPSReader(threading.Thread):
    def __init__(self, tx_queue, port="/dev/ttyS2", baud=9600):
        super().__init__(daemon=True)
        self.port, self.baud = port, baud
        self.tx_queue = tx_queue
        self._desconectar = False
        self.latitude = self.longitude = self.altitude = 0.0
        self.ser = None

    def solicitar_parada(self):
        self._desconectar = True

    @staticmethod
    def _to_decimal(value, direction):
        try:
            v   = float(value)
            deg = int(v / 100)
            dec = deg + (v - deg * 100) / 60.0
            return -dec if direction in ('S', 'W') else dec
        except Exception:
            return 0.0

    def run(self):
        try:
            self.ser = serial.Serial(self.port, self.baud, timeout=1)
            print(f"[GPS] Escuchando satélites en {self.port}")
        except Exception as e:
            print(f"[GPS] Error abriendo puerto: {e}"); return

        buf = ""
        last_gps_push = time.time()

        while not self._desconectar:
            try:
                if self.ser and self.ser.is_open:
                    buf += self.ser.read(256).decode(errors="ignore")
                    while "\n" in buf:
                        line, buf = buf.split("\n", 1)
                        line = line.strip()
                        if line.startswith(("$GNGGA", "$GPGGA")):
                            p = line.split(",")
                            if len(p) >= 10 and p[2] and p[4]:
                                self.latitude  = self._to_decimal(p[2], p[3])
                                self.longitude = self._to_decimal(p[4], p[5])
                                try:    self.altitude = float(p[9]) if p[9] else 0.0
                                except: self.altitude = 0.0

                                # Empujar a la cola cada ~2 segundos (evita saturar con datos repetidos)
                                if time.time() - last_gps_push > 2.0:
                                    paquete_gps = f"G,{self.latitude:.6f},{self.longitude:.6f},{self.altitude:.1f}"
                                    self.tx_queue.put(paquete_gps)
                                    last_gps_push = time.time()

            except Exception as e:
                print(f"[GPS] Error lectura: {e}")
                time.sleep(0.5)

        if self.ser and self.ser.is_open:
            self.ser.close()

# ---------------------------------------------------------------
#  Main Orquestador
# ---------------------------------------------------------------
if __name__ == "__main__":
    print("======================================================")
    print(" INICIANDO MULTIPLEXOR RADXA -> LORA ")
    print("======================================================")

    # Cola compartida entre GPS, STM32 y LORA
    tx_queue = queue.Queue()

    # IMPORTANTE: Hemos bajado el period a 1.0 en LoRaP2PSender para
    # que procese la cola más rápido ahora que tenemos múltiples sensores.
    lora  = LoRaP2PSender(q=tx_queue, port="/dev/ttyS4", baud=115200, period=1.0)
    gps   = GPSReader(tx_queue=tx_queue, port="/dev/ttyS2", baud=9600)
    stm32 = STM32Reader(tx_queue=tx_queue, port="/dev/ttyS7", baud=115200)

    # Iniciar hilos
    lora.start()
    gps.start()
    stm32.start()

    try:
        # El hilo principal se queda monitorizando que todo esté vivo
        while True:
            time.sleep(1.0)

    except KeyboardInterrupt:
        print("\n[Main] Deteniendo servicios...")
    finally:
        lora.solicitar_parada()
        gps.solicitar_parada()
        stm32.solicitar_parada()

        time.sleep(0.5)
        print("[Main] Todos los puertos liberados. Sistema apagado.")
