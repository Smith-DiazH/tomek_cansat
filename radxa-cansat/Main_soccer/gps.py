 #!/usr/bin/env python3
"""
gps.py  Lee NMEA por serial y actualiza RobotState.
"""
import serial
import threading
import time

GPS_PORT = "/dev/ttyS2"
GPS_BAUD = 9600


class GPSReader(threading.Thread):
    def __init__(self, robot_state, log_q=None,
                 port=GPS_PORT, baud=GPS_BAUD):
        super().__init__(daemon=True, name="GPS-Reader")
        self.state  = robot_state
        self.log_q  = log_q
        self.port   = port
        self.baud   = baud
        self._stop  = False

    def stop(self):
        self._stop = True

    @staticmethod
    def _to_decimal(value: str, direction: str) -> float:
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
            print(f"[GPS] Puerto abierto: {self.port} @ {self.baud}")
        except Exception as e:
            print(f"[GPS] No se pudo abrir {self.port}: {e}")
            return

        buf = ""
        while not self._stop:
            try:
                buf += ser.read(256).decode(errors="ignore")
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    line = line.strip()

                    if not line.startswith(("$GNGGA", "$GPGGA")):
                        continue

                    p = line.split(",")
                    if len(p) < 10 or not p[2] or not p[4]:
                        continue

                    lat = self._to_decimal(p[2], p[3])
                    lon = self._to_decimal(p[4], p[5])
                    try:
                        alt = float(p[9]) if p[9] else 0.0
                    except ValueError:
                        alt = 0.0

                    fix = p[6] != "0" if len(p) > 6 else False
                    self.state.update_gps(lat, lon, alt, fix)

                    if self.log_q:
                        self.log_q.put(
                            f"GPS: lat={lat:.6f} lon={lon:.6f} "
                            f"alt={alt:.1f} fix={fix}"
                        )

            except Exception as e:
                print(f"[GPS] Error: {e}")
                time.sleep(0.5)

        ser.close()
