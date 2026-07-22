import serial

ser = serial.Serial("/dev/ttyS2", 9600, timeout=1)

while True:
    data = ser.read(100)
    print(f"Leídos {len(data)} bytes:", data)

