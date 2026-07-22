#!/usr/bin/env python3
"""
uart.py  Comunicación con STM32: recibe IMU, envía PWM con rampa.
Incluye fail-safe: si no llega comando en `timeout_cmd` segundos, frena.
"""
import serial
import threading
import time

STM_PORT = "/dev/ttyS7"
STM_BAUD = 115200

from comandos import DIRECTIONS

class STM32UART(threading.Thread):
    def __init__(self, robot_state, log_q=None, port=STM_PORT, baud=STM_BAUD,
                 tiempo_rampa=0.5, ciclo=0.05, timeout_cmd=2.0):
        super().__init__(daemon=True, name="STM32-UART")
        self.state = robot_state
        self.log_q = log_q
        self.port  = port
        self.baud  = baud
        self._stop = False

        self.tiempo_rampa = tiempo_rampa
        self.ciclo = ciclo
        self.timeout_cmd = timeout_cmd

        self.v_actual_A = 0
        self.v_actual_B = 0
        self.v_origen_A = 0
        self.v_origen_B = 0
        self.dir_A = 0
        self.dir_B = 0
        self.inicio_rampa = time.time()
        self.last_command = 'S'
        self.failsafe_activo = False

    def stop(self):
        self._stop = True

    def run(self):
        try:
            self.ser = serial.Serial(self.port, self.baud, timeout=0.1)
            print(f"[UART] Puerto abierto: {self.port} @ {self.baud}")
        except Exception as e:
            print(f"[UART] No se pudo abrir {self.port}: {e}")
            return

        threading.Thread(target=self._read_loop, daemon=True).start()

        while not self._stop:
            self._actualizar_rampa()
            time.sleep(self.ciclo)

    def _read_loop(self):
        while not self._stop:
            try:
                line = self.ser.readline().decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                if line.startswith("Roll:"):
                    parts = line.replace("Roll:", "").replace("Pitch:", "") \
                                .replace("Yaw:", "").split()
                    if len(parts) == 3:
                        self.state.update_imu(float(parts[0]), float(parts[1]), float(parts[2]))
                        if self.log_q:
                            self.log_q.put(f"IMU: R={parts[0]} P={parts[1]} Y={parts[2]}")
            except Exception as e:
                print(f"[UART] Error leyendo: {e}")
                time.sleep(0.1)

    def _calcular_paso(self, v_inicio, v_final):
        transcurrido = time.time() - self.inicio_rampa
        if transcurrido >= self.tiempo_rampa:
            return v_final
        progreso = transcurrido / self.tiempo_rampa
        return int(v_inicio + progreso * (v_final - v_inicio))

    def _actualizar_rampa(self):
        cmd, edad_cmd = self.state.get_command()

        if edad_cmd > self.timeout_cmd:
            if not self.failsafe_activo:
                print(f"[UART] FAIL-SAFE activado: sin comando por {edad_cmd:.1f}s ? STOP")
                if self.log_q:
                    self.log_q.put("UART: FAIL-SAFE ? STOP")
                self.failsafe_activo = True
            cmd = 'S'
        else:
            if self.failsafe_activo:
                print("[UART] FAIL-SAFE liberado: comando recibido")
                self.failsafe_activo = False

        if cmd != self.last_command:
            self.v_origen_A = self.v_actual_A
            self.v_origen_B = self.v_actual_B
            self.inicio_rampa = time.time()
            self.last_command = cmd

        meta_A, dir_A, meta_B, dir_B = DIRECTIONS.get(cmd, (0, 0, 0, 0))
        self.dir_A = dir_A
        self.dir_B = dir_B

        self.v_actual_A = self._calcular_paso(self.v_origen_A, meta_A)
        self.v_actual_B = self._calcular_paso(self.v_origen_B, meta_B)

        self._send_motor_speeds(self.v_actual_A, self.dir_A, self.v_actual_B, self.dir_B)

    def _send_motor_speeds(self, pwm_a, dir_a, pwm_b, dir_b):
        cmd1 = f"{'f' if dir_a == 0 else 'r'}{pwm_a}"
        cmd2 = f"{'g' if dir_b == 0 else 'h'}{pwm_b}"
        try:
            self.ser.write((cmd1 + "\n").encode("utf-8"))
            self.ser.write((cmd2 + "\n").encode("utf-8"))
        except Exception as e:
            print(f"[UART] Error enviando: {e}")
