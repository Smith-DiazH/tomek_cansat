 
#!/usr/bin/env python3
"""
=============================================================================
MULTIPLEXOR BIDIRECCIONAL CON REGISTRO DE DATOS  Radxa CM4
=============================================================================
Este script orquesta múltiples fuentes de datos locales (GPS, STM32), las
transmite vía LoRa P2P, escucha comandos/datos entrantes desde la Raspberry Pi
y centraliza todo el tráfico en un archivo de texto secuencial (.txt).

ARQUITECTURA DE PUERTOS:
------------------------
- /dev/ttyS4 (UART4): Módulo LoRa RAK3172 (115200 baudios)
- /dev/ttyS2 (UART2): Módulo GPS NMEA      (9600 baudios)
- /dev/ttyS7 (UART7): Microcontrolador STM32 (115200 baudios) -> uart7_m0

CONTRATO DE DATOS ADICIONAL (Transmisión Base -> Radxa):
--------------------------------------------------------
El script asume que la Raspberry Pi enviará paquetes prefijados que serán
almacenados y procesados de igual forma (ej. comandos de control 'C,', etc.).
=============================================================================
"""
import time
import queue
import threading
import binascii
import serial
import os

# Nombre del archivo de registros
LOG_FILE = "registro_telemetria.txt"

# ---------------------------------------------------------------
#  1. Hilo de Escritura en Disco Asíncrona (LogWriter)
# ---------------------------------------------------------------
class LogWriter(threading.Thread):
    def __init__(self, log_q, file_path=LOG_FILE):
        super().__init__(daemon=True)
        self.log_q = log_q
        self.file_path = file_path
        self._desconectar = False

    def solicitar_parada(self):
        self._desconectar = True

    def run(self):
        print(f"[LogWriter] Guardando registros en: {os.path.abspath(self.file_path)}")
        while not self._desconectar or not self.log_q.empty():
            try:
                # Esperar entrada de datos con un timeout para revisar la condición de parada
                linea = self.log_q.get(timeout=0.5)
                timestamp = time.strftime("%Y-%m-%d %H:%M:%S")

                with open(self.file_path, "a", encoding="utf-8") as f:
                    f.write(f"[{timestamp}] {linea}\n")

                self.log_q.task_done()
            except queue.Empty:
                pass
            except Exception as e:
                print(f"[LogWriter] Error escribiendo en disco: {e}")

# ---------------------------------------------------------------
#  2. Hilo Transceptor LoRa P2P (Bidireccional Inteligente)
# ---------------------------------------------------------------
class LoRaP2PTransceiver(threading.Thread):
    def __init__(self, tx_q, log_q, port="/dev/ttyS4", baud=115200,
                 p2p="915000000:7:0:0:8:22", period=1.0):
        super().__init__(daemon=True)
        self.tx_q = tx_q
        self.log_q = log_q
        self.port, self.baud = port, baud
        self.p2p, self.period = p2p, period
        self._desconectar = False
        self.ser = None

    def solicitar_parada(self):
        self._desconectar = True

    def _at(self, cmd, wait=0.1):
        if self.ser and self.ser.is_open:
            self.ser.write((cmd + "\r\n").encode())
            self.ser.flush()
            time.sleep(wait)
            respuesta = self.ser.read(self.ser.in_waiting or 1).decode(errors="ignore").strip()
            if "ERROR" in respuesta or "BUSY" in respuesta:
                print(f"?? [MÓDEM RAK - ALERTA]: '{cmd}' devolvió:\n{respuesta}")
            return respuesta
        return ""

    def _rearm_rx(self):
        """Pone al módulo en modo escucha continua de forma segura."""
        self._at("AT+PRECV=0", wait=0.05)
        self._at("AT+PRECV=65535", wait=0.05)

    def _send(self, text):
        """Apaga escucha, transmite esperando que el chip termine y re-escucha."""
        self._at("AT+PRECV=0", wait=0.05)
        # Enviamos y damos un margen de 0.25s para que el RAK haga el envío físico
        self._at(f"AT+PSEND={binascii.hexlify(text.encode()).decode()}", wait=0.25)
        self._rearm_rx()

    def run(self):
        try:
            self.ser = serial.Serial(self.port, self.baud, timeout=0.01) # Timeout bajo para lecturas rápidas

            self.ser.write(b"AT\r\n")
            time.sleep(0.1)
            if "OK" not in self.ser.read(self.ser.in_waiting).decode():
                print(f"? [LoRa] Módulo no detectado en {self.port}. Abortando.")
                return

            self._at("AT+NWM=0")
            self._at(f"AT+P2P={self.p2p}")
            self._rearm_rx()
            print(f"[LoRa] Transceptor P2P listo y equilibrado en {self.port}")
        except Exception as e:
            print(f"[LoRa] Error Fatal: {e}"); return

        last_tx_time = 0.0
        buf = ""

        while not self._desconectar:
            try:
                # --- FASE 1: LECTURA CONTINUA (RX) ---
                # Pasamos la mayor parte del tiempo leyendo el puerto serie en ráfagas cortas
                t_fin_escucha = time.time() + 0.1  # Ventana de escucha activa de 100ms por ciclo
                while time.time() < t_fin_escucha:
                    if self.ser.in_waiting > 0:
                        buf += self.ser.read(self.ser.in_waiting).decode(errors="ignore")

                    while "\n" in buf:
                        line, buf = buf.split("\n", 1)
                        line = line.strip()
                        if not line: continue

                        if "+EVT:RXP2P:" in line:
                            hexpl = line.split(":")[-1]
                            try:
                                payload_remoto = binascii.unhexlify(hexpl).decode("utf-8", errors="ignore")
                                print(f"?? [RX LORA BASE] -> {payload_remoto}")
                                self.log_q.put(f"REMOTO_RX: {payload_remoto}")
                            except Exception:
                                pass

                        if "BUSY" in line or "P2P_RX_ON" in line or "+EVT:RXP2P:" in line:
                            self._rearm_rx()

                    time.sleep(0.01)

                # --- FASE 2: TRANSMISIÓN (TX CORTO) ---
                # Solo enviamos UN paquete por ciclo si ya pasó el periodo configurado
                if time.time() - last_tx_time >= self.period:
                    try:
                        payload = self.tx_q.get_nowait()
                        self._send(payload.strip())
                        last_tx_time = time.time()
                        print(f"?? [TX LORA] {payload.strip()}")
                        self.tx_q.task_done()
                    except queue.Empty:
                        pass

            except Exception as e:
                print(f"[LoRa] Error en ciclo principal: {e}")
                time.sleep(0.5)

        if self.ser and self.ser.is_open:
            self.ser.close()

# ---------------------------------------------------------------
#  3. Hilo STM32 (Lector del IMU A/Y/M)
# ---------------------------------------------------------------
class STM32Reader(threading.Thread):
    def __init__(self, tx_queue, log_queue, port="/dev/ttyS7", baud=115200):
        super().__init__(daemon=True)
        self.port, self.baud = port, baud
        self.tx_queue = tx_queue
        self.log_queue = log_queue
        self._desconectar = False
        self.ser = None

    def solicitar_parada(self):
        self._desconectar = True

    def run(self):
        try:
            self.ser = serial.Serial(self.port, self.baud, timeout=1)
            print(f"[STM32] Escuchando IMU en {self.port} (uart7_m0)")
        except Exception as e:
            print(f"[STM32] Error STM32: {e}"); return

        buf = ""
        while not self._desconectar:
            try:
                if self.ser and self.ser.is_open:
                    buf += self.ser.read(256).decode(errors="ignore")
                    while "\n" in buf:
                        line, buf = buf.split("\n", 1)
                        line = line.strip()

                        if line.startswith(("A,", "Y,", "M,")):
                            self.tx_queue.put(line)
                            # También lo registramos inmediatamente de forma local
                            self.log_queue.put(f"LOCAL_IMU: {line}")
            except Exception as e:
                print(f"[STM32] Error: {e}")
                time.sleep(0.5)

# ---------------------------------------------------------------
#  4. Hilo GPS (Generador de Prefijo G)
# ---------------------------------------------------------------
class GPSReader(threading.Thread):
    def __init__(self, tx_queue, log_queue, port="/dev/ttyS2", baud=9600):
        super().__init__(daemon=True)
        self.port, self.baud = port, baud
        self.tx_queue = tx_queue
        self.log_queue = log_queue
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
            print(f"[GPS] Error GPS: {e}"); return

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

                                if time.time() - last_gps_push > 2.0:
                                    paquete_gps = f"G,{self.latitude:.6f},{self.longitude:.6f},{self.altitude:.1f}"
                                    self.tx_queue.put(paquete_gps)
                                    self.log_queue.put(f"LOCAL_GPS: {paquete_gps}")
                                    last_gps_push = time.time()
            except Exception as e:
                print(f"[GPS] Error: {e}")
                time.sleep(0.5)

# ---------------------------------------------------------------
#  Orquestador Central
# ---------------------------------------------------------------
if __name__ == "__main__":
    print("======================================================")
    print(" INICIANDO NODO COORDENADOR MULTIPLEXOR BIDIRECCIONAL ")
    print("======================================================")

    tx_queue = queue.Queue()
    log_queue = queue.Queue()

    # Instanciación de hilos
    writer = LogWriter(log_q=log_queue)
    lora   = LoRaP2PTransceiver(tx_q=tx_queue, log_q=log_queue, period=1.0)
    gps    = GPSReader(tx_queue=tx_queue, log_queue=log_queue)
    stm32  = STM32Reader(tx_queue=tx_queue, log_queue=log_queue)

    # Inicialización en cascada
    writer.start()
    lora.start()
    gps.start()
    stm32.start()

    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\n[Main] Interrupción por teclado capturada. Apagando...")
    finally:
        lora.solicitar_parada()
        gps.solicitar_parada()
        stm32.solicitar_parada()
        writer.solicitar_parada()

        # Esperar a que la cola de logs termine de vaciarse en el archivo
        time.sleep(0.8)
        print("[Main] Registro completado y hardware liberado de forma segura.")
