#!/usr/bin/env python3
import serial
import time

ser = serial.Serial('/dev/ttyS7', 115200, timeout=1)

print("Esperando boot completo del STM32...")
time.sleep(3)
ser.reset_input_buffer()
print("Listo.\n")

def drain_quiet(duration):
    """Lee y descarta silenciosamente (para vaciar el buffer sin llenar pantalla)."""
    t_end = time.time() + duration
    while time.time() < t_end:
        ser.readline()

def send_and_wait(cmd, wait=1.0):
    print(f">>> Enviando {cmd.strip()}")
    ser.write(cmd.encode())
    t_end = time.time() + wait
    while time.time() < t_end:
        line = ser.readline().decode(errors="replace").strip()
        if not line:
            continue
        if line.startswith("Roll:"):
            continue   # ? filtra el ruido del IMU
        print(f"    [STM32] {line}")

drain_quiet(0.3)  # limpia lo último del boot sin imprimir nada

send_and_wait("f200\n", wait=1.0)
send_and_wait("s\n", wait=0.5)

send_and_wait("g200\n", wait=1.0)
send_and_wait("t\n", wait=0.5)

ser.close()
