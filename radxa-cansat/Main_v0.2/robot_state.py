import threading
import time

class RobotState:
    def __init__(self):
        self._lock = threading.Lock()

        # IMU (STM32 ? Radxa, binario)
        self.yaw   = 0.0
        self.pitch = 0.0
        self.roll  = 0.0
        self.stm32_ok      = False
        self.stm32_last_rx = 0.0

        # Encoders / velocidades rueda (STM32 ? Radxa)
        self.left_speed  = 0.0
        self.right_speed = 0.0

        # GPS (Radxa lee directo)
        self.latitude    = 0.0
        self.longitude   = 0.0
        self.altitude    = 0.0
        self.gps_fix     = False
        self.gps_last_rx = 0.0

        # Target de navegación (llega por LoRa desde la base)
        self.target_lat    = None   # None = sin target todavía
        self.target_lon    = None
        self.target_updated = False  # flag para que navigation.py sepa que cambió

        # Comando de navegación (navigation.py ? uart.py TX)
        self.cmd_vl = 0.0
        self.cmd_vr = 0.0

    # ------------------------------------------------------------------
    # Escrituras atómicas
    # ------------------------------------------------------------------
    def update_imu(self, yaw: float, pitch: float, roll: float):
        with self._lock:
            self.yaw, self.pitch, self.roll = yaw, pitch, roll
            self.stm32_ok      = True
            self.stm32_last_rx = time.time()

    def update_speeds(self, left: float, right: float):
        with self._lock:
            self.left_speed  = left
            self.right_speed = right

    def update_gps(self, lat: float, lon: float, alt: float, fix: bool):
        with self._lock:
            self.latitude    = lat
            self.longitude   = lon
            self.altitude    = alt
            self.gps_fix     = fix
            self.gps_last_rx = time.time()

    def update_target(self, lat: float, lon: float):
        with self._lock:
            self.target_lat     = lat
            self.target_lon     = lon
            self.target_updated = True
        print(f"[STATE] Nuevo target: {lat:.6f}, {lon:.6f}")

    def consume_target_flag(self) -> bool:
        """navigation.py llama esto para saber si el target cambió."""
        with self._lock:
            changed = self.target_updated
            self.target_updated = False
            return changed

    def set_motor_command(self, vl: float, vr: float):
        with self._lock:
            self.cmd_vl = vl
            self.cmd_vr = vr

    def get_motor_command(self):
        with self._lock:
            return self.cmd_vl, self.cmd_vr

    def snapshot(self) -> dict:
        """Copia atómica  la usa LoRa TX para armar el paquete de telemetría."""
        with self._lock:
            return {
                "yaw":   self.yaw,
                "pitch": self.pitch,
                "roll":  self.roll,
                "left_speed":  self.left_speed,
                "right_speed": self.right_speed,
                "latitude":    self.latitude,
                "longitude":   self.longitude,
                "altitude":    self.altitude,
                "gps_fix":     self.gps_fix,
                "cmd_vl":      self.cmd_vl,
                "cmd_vr":      self.cmd_vr,
                "target_lat":  self.target_lat,
                "target_lon":  self.target_lon,
                "stm32_ok":    self.stm32_ok,
            }
