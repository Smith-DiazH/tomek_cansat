#!/usr/bin/env python3
"""
robot_state.py  Estado compartido thread-safe del robot.
"""
import threading
import time

class RobotState:
    def __init__(self):
        self._lock = threading.Lock()

        # IMU
        self.roll = 0.0
        self.pitch = 0.0
        self.yaw = 0.0

        # GPS
        self.lat = 0.0
        self.lon = 0.0
        self.alt = 0.0
        self.gps_fix = False

        # Comando de movimiento actual
        self.command = 'S'
        self.last_cmd_time = time.time()

    def update_imu(self, roll, pitch, yaw):
        with self._lock:
            self.roll = roll
            self.pitch = pitch
            self.yaw = yaw

    def update_gps(self, lat, lon, alt, fix):
        with self._lock:
            self.lat = lat
            self.lon = lon
            self.alt = alt
            self.gps_fix = fix

    def set_command(self, cmd):
        with self._lock:
            self.command = cmd
            self.last_cmd_time = time.time()

    def get_command(self):
        """Devuelve (comando, segundos_desde_ultimo_comando) de forma segura."""
        with self._lock:
            return self.command, time.time() - self.last_cmd_time

    def snapshot(self):
        """Copia segura de todo el estado para telemetría."""
        with self._lock:
            return {
                "roll": self.roll, "pitch": self.pitch, "yaw": self.yaw,
                "lat": self.lat, "lon": self.lon, "alt": self.alt,
                "gps_fix": self.gps_fix,
                "command": self.command,
            }
