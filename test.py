#!/usr/bin/env python3
"""
SENDER GPS  Radxa CM4
Envía solo coordenadas GPS por LoRa P2P cada 2 segundos.
Formato del paquete: lat,lon,alt
"""
import time
import queue
import threading
import binascii
import serial

# ---------------------------------------------------------------
#  LoRa P2P Sender
# ---------------------------------------------------------------
class LoRaP2PSender(threading.Thread):
    def __init__(self, q, port="/dev/ttyS2", baud=115200,
                 p2p="915000000:7:125:0:8:22", period=2.0):
        super().__init__(daemon=True)
        self.q, self.port, self.baud = q, port, baud
        self.p2p, self.period = p2p, period
        self._stop = False
        self.ser   = None

    def stop(self): self._stop = True

    def _at(self, cmd, wait=0.25):
        if self.ser:
            self.ser.write((cmd + "\r\n").encode())
            self.ser.flush()
            time.sleep(wait)

    def _send(self, text):
        self._at(f"AT+PSEND={binascii.hexlify(text.encode()).decode()}", wait=0.4)

    def run(self):
        try:
            self.ser = serial.Serial(self.port, self.baud, timeout=0.2)
            self._at("AT")
            self._at("AT+PRECV=0")
            self._at("AT+NWM=0")
            self._at(f"AT+P2P={self.p2p}")
            print(f"[LoRa] Listo en {self.port}")
        except Exception as e:
            print(f"[LoRa] Error: {e}"); return

        last = 0.0
        while not self._stop:
            try:
                payload = None
                try:
                    payload = self.q.get(timeout=self.period)
                except queue.Empty:
                    pass
                if payload:
                    dt = time.time() - last
                    if dt < self.period:
                        time.sleep(self.period - dt)
                    self._send(payload.strip())
                    last = time.time()
                    print(f"[LoRa] TX ? {payload.strip()}")
            except Exception as e:
                print(f"[LoRa] Error envío: {e}")
                time.sleep(0.5)

        if self.ser: self.ser.close()


# ---------------------------------------------------------------
#  GPS (Corregido con readline)
# ---------------------------------------------------------------
class GPS(threading.Thread):
    def __init__(self, port="/dev/ttyS4", baud=9600):
        super().__init__(daemon=True)
        self.port, self.baud = port, baud
        self._stop = False
        self.latitude = self.longitude = self.altitude = 0.0

    def stop(self): self._stop = True

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
            ser = serial.Serial(self.port, self.baud, timeout=1)
        except Exception as e:
            print(f"[GPS] Error: {e}"); return

        while not self._stop:
            try:
                # Utilizamos tu método comprobado de readline()
                line = ser.readline().decode(errors="ignore").strip()
                
                if line and line.startswith(("$GNGGA", "$GPGGA")):
                    p = line.split(",")
                    # Validamos que la trama tenga datos antes de parsear
                    if len(p) >= 10 and p[2] and p[4]:
                        self.latitude  = self._to_decimal(p[2], p[3])
                        self.longitude = self._to_decimal(p[4], p[5])
                        try:    
                            self.altitude = float(p[9]) if p[9] else 0.0
                        except: 
                            self.altitude = 0.0
            except Exception as e:
                print(f"[GPS] Error lectura: {e}")
                time.sleep(0.5)
        ser.close()


# ---------------------------------------------------------------
#  Main
# ---------------------------------------------------------------
if __name__ == "__main__":
    print("=== TELEMETRÍA GPS ? LoRa ===")

    tx_queue = queue.Queue()
    lora = LoRaP2PSender(q=tx_queue, port="/dev/ttyS2", baud=115200, period=2.0)
    gps  = GPS(port="/dev/ttyS4", baud=9600)

    lora.start()
    gps.start()
    time.sleep(2)

    try:
        while True:
            lat, lon, alt = gps.latitude, gps.longitude, gps.altitude
            
            # Condicional de seguridad (requiere línea de visión al cielo)
            if lat != 0.0 and lon != 0.0:
                tx_queue.put(f"{lat:.6f},{lon:.6f},{alt:.1f}")
                print(f"[Main] Encolado ? lat={lat:.6f}  lon={lon:.6f}  alt={alt:.1f} m")
            else:
                print("[Main] Esperando fix GPS (buscando satélites)...")
            time.sleep(2.0)

    except KeyboardInterrupt:
        print("\n[Main] Deteniendo...")
    finally:
        lora.stop()
        gps.stop()
