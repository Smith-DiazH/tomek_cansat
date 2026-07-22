#!/usr/bin/env python3
"""
PING SENDER  Radxa CM4
Envía "HOLA" cada 3 segundos por LoRa P2P.
"""
import serial, time, binascii

PORT = "/dev/ttyS2"
BAUD = 115200
P2P  = "915000000:7:125:0:8:22"
MSG  = "Dia de hoy"

def at(ser, cmd, wait=0.3):
    ser.write((cmd + "\r\n").encode())
    ser.flush()
    time.sleep(wait)
    r = ser.read(ser.in_waiting or 1).decode(errors="ignore").strip()
    print(f"  > {cmd}  ?  {r}")
    return r

with serial.Serial(PORT, BAUD, timeout=0.5) as s:
    print("=== PING SENDER ===\n")
    at(s, "AT")
    at(s, "AT+PRECV=0")
    at(s, "AT+NWM=0")
    at(s, f"AT+P2P={P2P}")
    print("\nEnviando...\n")

    n = 0
    while True:
        n += 1
        payload = f"{MSG}:{n}"
        hexdata = binascii.hexlify(payload.encode()).decode()
        print(f"[#{n}] Enviando '{payload}'")
        at(s, f"AT+PSEND={hexdata}", wait=0.5)
        time.sleep(3)
