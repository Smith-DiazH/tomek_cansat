 
#!/usr/bin/env python3
"""
test_gps.py
Prueba del GPSReader.
"""

import time
from gps import GPSReader


class RobotState:
    def __init__(self):
        self.lat = 0.0
        self.lon = 0.0
        self.alt = 0.0
        self.fix = False

    def update_gps(self, lat, lon, alt, fix):
        self.lat = lat
        self.lon = lon
        self.alt = alt
        self.fix = fix


def main():
    state = RobotState()

    gps = GPSReader(state)
    gps.start()

    print("Esperando datos del GPS... (Ctrl+C para salir)\n")

    try:
        while True:
            print(
                f"\rFix: {state.fix} | "
                f"Lat: {state.lat:.6f} | "
                f"Lon: {state.lon:.6f} | "
                f"Alt: {state.alt:.2f} m",
                end="",
                flush=True,
            )
            time.sleep(1)

    except KeyboardInterrupt:
        print("\nDeteniendo GPS...")
        gps.stop()
        gps.join()


if __name__ == "__main__":
    main()
