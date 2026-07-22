#!/usr/bin/env python3
"""
navigation.py  Control de rumbo PID para robot diferencial.

Entradas  (de RobotState):
    latitude, longitude    posición actual (GPS)
    yaw                    rumbo actual en grados (IMU, BNO085 vía STM32)
    target_lat, target_lon  destino (llega por LoRa)

Salidas (a RobotState):
    cmd_vl, cmd_vr         velocidades angulares de rueda [rad/s]
                            el STM32 recibe estos valores y hace su PID interno

Parámetros del robot (ajustar según tu hardware):
    WHEEL_RADIUS    r  = 0.09  m
    WHEEL_BASE      b  = 0.23  m
    BASE_SPEED      v  = 0.6   m/s
    MAX_WHEEL_SPEED    = 10.0  rad/s
"""

import math

# -- Parámetros físicos ------------------------------------------------------
WHEEL_RADIUS    = 0.09    # r  [m]
WHEEL_BASE      = 0.23    # b  [m]
BASE_SPEED      = 0.6     # v  [m/s]   velocidad lineal máxima (se escala por error angular)
MAX_WHEEL_SPEED = 10.0    # ?max por rueda [rad/s]

# -- Ganancias PID -----------------------------------------------------------
KP = 4.0
KI = 0.001
KD = 0.1

# -- Anti-windup: solo integra si el error es moderado ----------------------
INTEGRAL_ERROR_LIMIT = 5.0      # saturación integral [rad]
INTEGRAL_ACTIVE_ZONE = 0.5      # |e| < 0.5 rad para acumular integral

# -- Llegada a destino --------------------------------------------------------
# Validar en campo: 4 m es un punto de partida razonable para absorber el
# ruido típico de un fix GPS estándar (2-5 m). Si en campo ves que el robot
# "llega" de forma inestable (entra y sale del radio), subir este valor.
ARRIVAL_RADIUS_M = 4.0

EARTH_RADIUS_M = 6371000.0


def _bearing_to(lat1_deg, lon1_deg, lat2_deg, lon2_deg) -> float:
    """
    Rumbo inicial desde (lat1, lon1) hacia (lat2, lon2).
    Devuelve ángulo en radianes, normalizado a (-p, p].
    Fórmula esférica estándar (igual que bearingTo() de tu código anterior).
    """
    lat1 = math.radians(lat1_deg)
    lat2 = math.radians(lat2_deg)
    dlon = math.radians(lon2_deg - lon1_deg)

    x = (math.cos(lat1) * math.sin(lat2)
         - math.sin(lat1) * math.cos(lat2) * math.cos(dlon))
    y = math.sin(dlon) * math.cos(lat2)

    return math.atan2(y, x)   # ya normalizado a (-p, p]


def _distance_m(lat1_deg, lon1_deg, lat2_deg, lon2_deg) -> float:
    """
    Distancia entre dos coordenadas (Haversine), en metros.
    Suficiente para distancias cortas tipo CanSat; no requiere modelo
    elipsoidal (WGS84) para este caso de uso.
    """
    lat1 = math.radians(lat1_deg)
    lat2 = math.radians(lat2_deg)
    dlat = math.radians(lat2_deg - lat1_deg)
    dlon = math.radians(lon2_deg - lon1_deg)

    a = (math.sin(dlat / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return EARTH_RADIUS_M * c


def _wrap(angle: float) -> float:
    """Normaliza un ángulo al intervalo (-p, p]."""
    return math.atan2(math.sin(angle), math.cos(angle))


def _unicycle_to_wheels(v: float, w: float):
    """
    Convierte (v [m/s], ? [rad/s]) a velocidades angulares de rueda [rad/s].
    ?L = (2v + ?·b) / (2r)
    ?R = (2v - ?·b) / (2r)
    Aplica saturación conservando la relación entre ruedas (escalado uniforme).
    """
    w_max = (2 * WHEEL_RADIUS * MAX_WHEEL_SPEED) / WHEEL_BASE
    w = max(-w_max, min(w_max, w))

    omega_l = (2 * v + w * WHEEL_BASE) / (2 * WHEEL_RADIUS)
    omega_r = (2 * v - w * WHEEL_BASE) / (2 * WHEEL_RADIUS)

    # Escalado uniforme si alguna rueda excede el límite
    max_raw = max(abs(omega_l), abs(omega_r))
    if max_raw > MAX_WHEEL_SPEED:
        scale   = MAX_WHEEL_SPEED / max_raw
        omega_l *= scale
        omega_r *= scale

    return omega_l, omega_r


class NavigationController:
    """
    Uso desde main.py:

        nav = NavigationController()
        # en el bucle a 20 Hz:
        nav.step(state, dt)

        # llamar siempre que cambie el target (nuevo paquete LoRa con
        # target_lat/target_lon distintos a los anteriores):
        nav.reset()
    """

    def __init__(self):
        self._integral   = 0.0
        self._last_error = 0.0
        self.arrived      = False   # expuesto para que main.py lo consulte/loggee

    def reset(self):
        """Llamar cuando cambia el target para evitar windup acumulado."""
        self._integral   = 0.0
        self._last_error = 0.0
        self.arrived      = False

    def step(self, state, dt: float):
        """
        Un ciclo de control. Escribe cmd_vl y cmd_vr en robot_state.
        dt: tiempo transcurrido desde el último ciclo [s]
        """
        if dt <= 0:
            dt = 0.001

        # -- Sin target: parar -----------------------------------------------
        if state.target_lat is None or state.target_lon is None:
            state.set_motor_command(0.0, 0.0)
            return

        # -- Sin GPS: avanzar recto (comportamiento failsafe del PDF) --------
        if not state.gps_fix:
            vl, vr = _unicycle_to_wheels(BASE_SPEED, 0.0)
            state.set_motor_command(vl, vr)
            return

        # -- Leer estado (snapshot atómico) ----------------------------------
        with state._lock:
            lat  = state.latitude
            lon  = state.longitude
            yaw  = state.yaw           # grados, del BNO085
            t_lat = state.target_lat
            t_lon = state.target_lon

        # -- Distancia al destino: ¿ya llegamos? ------------------------------
        distance = _distance_m(lat, lon, t_lat, t_lon)
        if distance <= ARRIVAL_RADIUS_M:
            if not self.arrived:
                self.arrived = True
            state.set_motor_command(0.0, 0.0)
            return
        else:
            self.arrived = False

        # -- Bearing hacia el destino -----------------------------------------
        theta_ref = _bearing_to(lat, lon, t_lat, t_lon)

        # -- Rumbo actual en radianes -----------------------------------------
        theta_now = _wrap(math.radians(yaw))

        # -- Error angular normalizado ----------------------------------------
        error = _wrap(theta_ref - theta_now)

        # -- PID -------------------------------------------------------------
        # Integral con anti-windup
        if abs(error) < INTEGRAL_ACTIVE_ZONE:
            self._integral += error * dt
            self._integral  = max(-INTEGRAL_ERROR_LIMIT,
                                   min(INTEGRAL_ERROR_LIMIT, self._integral))
        else:
            self._integral = 0.0   # reset si el error es grande

        # Derivada  error_diff envuelto para evitar picos falsos al cruzar
        # la discontinuidad +-pi (p.ej. error pasa de +3.0 rad a -3.0 rad
        # entre ciclos sin que el rumbo real haya cambiado tanto)
        error_diff = _wrap(error - self._last_error)
        derivative = error_diff / dt
        self._last_error = error

        omega = KP * error + KI * self._integral + KD * derivative

        # -- Velocidad lineal escalada por error angular -----------------------
        # error=0   -> v = BASE_SPEED (avance pleno)
        # error=90  -> v = 0          (pivotea en el sitio)
        # error=180 -> v = 0          (no retrocede, solo gira)
        v = BASE_SPEED * max(0.0, math.cos(error))

        # -- Convertir a velocidades de rueda ---------------------------------
        vl, vr = _unicycle_to_wheels(v, omega)

        state.set_motor_command(vl, vr)
