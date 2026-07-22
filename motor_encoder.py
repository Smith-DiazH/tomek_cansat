import serial
import threading
import sys

# Configuración UART
UART_PORT = "/dev/ttyS7"
BAUDRATE = 115200

# Abrir puerto serie
try:
    ser = serial.Serial(
        port=UART_PORT,
        baudrate=BAUDRATE,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=0.1
    )
except Exception as e:
    print(f"Error abriendo UART: {e}")
    sys.exit(1)

print(f"Conectado a {UART_PORT} @ {BAUDRATE}")
print()
print("Comandos disponibles:")
print("  f120  -> Motor adelante PWM=120")
print("  r120  -> Motor reversa PWM=120")
print("  s     -> Stop")
print("  q     -> Salir")
print()


def uart_reader():
    """
    Lee continuamente mensajes enviados por el STM32.
    """
    while True:
        try:
            line = ser.readline().decode("utf-8", errors="ignore").strip()

            if line:
                print(f"\nSTM32 > {line}")

        except Exception as e:
            print(f"\nError de recepción: {e}")
            break


# Hilo de recepción
rx_thread = threading.Thread(
    target=uart_reader,
    daemon=True
)
rx_thread.start()


# Bucle principal
while True:
    try:
        cmd = input("CMD > ").strip()

        if cmd.lower() == "q":
            break

        ser.write((cmd + "\r\n").encode("utf-8"))

    except KeyboardInterrupt:
        break

    except Exception as e:
        print(f"Error enviando comando: {e}")


ser.close()
print("Puerto UART cerrado.")
