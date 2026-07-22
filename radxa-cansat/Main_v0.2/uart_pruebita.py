import serial

ser = serial.Serial('/dev/ttyS7', 115200, timeout=1)  # ajusta baudrate

print("Leyendo datos del STM32...")
try:
    while True:
        linea = ser.readline().decode('utf-8', errors='replace').strip()
        if linea:
            print(linea)
except KeyboardInterrupt:
    print("\nDetenido")
finally:
    ser.close()
