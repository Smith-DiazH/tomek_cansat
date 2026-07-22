#!/usr/bin/env python3
from serial import Serial
import time
import threading

class SphericalPoint:
    def __init__(self, latitude, longitude):
        self.latitude = latitude
        self.longitude = longitude

class GPS:
    GGA_TYPE = 'GGA'

    def __init__(self, port="/dev/ttyS4", baud=9600, timeout=0.5):
        self.port = port
        self.baud = baud

        # Agregamos timeout estricto a la lectura serial para evitar congelamientos
        self.serial = Serial(
            port=port,
            baudrate=baud,
            bytesize=8,
            parity='N',
            stopbits=1,
            timeout=timeout
        )

        self.last_point = SphericalPoint(0.0, 0.0)
        self.last_alt = 0.0
        self._stop_thread = False
        self.debug = False  # Forzado a True para ver qué pasa en consola

        self._thread = threading.Thread(target=self._update_loop, daemon=True)
        self._thread.start()

    def _update_loop(self):
        while not self._stop_thread:
            try:
                point, alt = self.read()
                if point.latitude != 0.0 or point.longitude != 0.0:
                    self.last_point = point
                    self.last_alt = alt
            except Exception as e:
                if self.debug:
                    print(f"[GPS Error Hilo]: {e}")
            time.sleep(0.1)

    def parse_nmea_sentence(self, sentence):
        parsed_sentence = {'type': ''}
        values = sentence.split(',')

        if len(values) > 0 and 'GGA' in values[0]:
            parsed_sentence['type'] = self.GGA_TYPE

            # Latitud
            if len(values) > 3 and values[2] and values[3]:
                try:
                    latitude = int(values[2][:2]) + float(values[2][2:]) / 60.0
                    if values[3] == 'S':
                        latitude = -latitude
                    parsed_sentence['latitude'] = latitude
                except Exception:
                    pass

            # Longitud
            if len(values) > 5 and values[4] and values[5]:
                try:
                    longitude = int(values[4][:3]) + float(values[4][3:]) / 60.0
                    if values[5] == 'W':
                        longitude = -longitude
                    parsed_sentence['longitude'] = longitude
                except Exception:
                    pass

            # Altitud
            if len(values) > 9 and values[9]:
                try:
                    parsed_sentence['altitude'] = float(values[9])
                except ValueError:
                    pass

        return parsed_sentence

    def read(self):
        parsed_sentence = {}
        try:
            # Lee lo que haya en el buffer actual
            data = self.serial.readline()
            if data:
                sentence = data.decode('utf-8', errors='ignore').strip()
                if sentence.startswith("$") and 'GGA' in sentence:
                    if self.debug:
                        print(f"[GPS Raw]: {sentence}") # Ver la trama procesada
                    parsed_sentence = self.parse_nmea_sentence(sentence)
        except Exception as e:
            if self.debug:
                print(f"[GPS Error Lectura]: {e}")

        lat = parsed_sentence.get('latitude', 0.0)
        lon = parsed_sentence.get('longitude', 0.0)
        alt = parsed_sentence.get('altitude', 0.0)

        if lat != 0.0:
            try:
                with open("gps_data.txt", "w") as f:
                    f.write(f"{lat:.6f},{lon:.6f}\n")
            except Exception:
                pass

        return SphericalPoint(lat, lon), alt

    def stop(self):
        self._stop_thread = True
        # Cerramos el puerto serie para desbloquear cualquier readline() colgado de inmediato
        try:
            self.serial.close()
        except Exception:
            pass
        if self._thread.is_alive():
            self._thread.join(timeout=1.0)


if __name__ == '__main__':
    # Forzamos los parámetros nativos de tu lectura limpia: ttyS4 a 9600 baudios
    gps = GPS(port="/dev/ttyS4", baud=9600)

    print("=== Test de Adquisición de Datos GPS (Presiona Ctrl+C para salir) ===")
    try:
        while True:
            lp = gps.last_point
            alt = gps.last_alt
            print(f"DATOS ACTUALES -> Lat: {lp.latitude:.6f} | Lon: {lp.longitude:.6f} | Alt: {alt:.1f} m")
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\n[INFO] Deteniendo monitoreo por solicitud del usuario.")
    finally:
        gps.stop()
        print("[INFO] Finalizado.")
