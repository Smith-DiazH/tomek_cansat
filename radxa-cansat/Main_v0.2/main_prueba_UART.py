#!/usr/bin/env python3
"""
main_prueba_UART.py — Script de debug exclusivo para comunicación UART Radxa ↔ STM32

RX (STM32 → Radxa): [0xAA][0x55][yaw][pitch][roll][left_spd][right_spd][CRC16]
                      2 + 5×4 + 2 = 24 bytes

TX (Radxa → STM32): [0xAA][0x55][VL][VR][CRC16]
                      2 + 2×4 + 2 = 12 bytes

Uso:
    python main_prueba_UART.py
    Ctrl+C para salir
"""

import serial
import struct
import time
import threading

# ─── Config ──────────────────────────────────────────────────────────────────
PORT      = "/dev/ttyS7"
BAUDRATE  = 115200
TIMEOUT   = 0.1

HEADER         = b'\xAA\x55'
RX_N_FLOATS    = 5                          # yaw, pitch, roll, left_spd, right_spd
RX_PACKET_SIZE = 2 + RX_N_FLOATS * 4 + 2    # 24 bytes
TX_PACKET_SIZE = 2 + 2 * 4 + 2              # 12 bytes

# ─── CRC-16/CCITT-FALSE ─────────────────────────────────────────────────────
def crc16(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = (crc << 1) ^ 0x1021 if crc & 0x8000 else crc << 1
            crc &= 0xFFFF
    return crc

# ─── Contadores globales ─────────────────────────────────────────────────────
stats = {
    "packets_ok": 0,
    "crc_errors": 0,
    "header_not_found": 0,
    "bytes_read": 0,
}

# ─── Impresión bonita del paquete ────────────────────────────────────────────
def print_packet(yaw, pitch, roll, left_spd, right_spd, raw_hex: str):
    print(
        f"\033[32m[OK]\033[0m  "
        f"YAW={yaw:+8.2f}°  "
        f"PITCH={pitch:+8.2f}°  "
        f"ROLL={roll:+8.2f}°  "
        f"L_SPD={left_spd:+7.3f}  "
        f"R_SPD={right_spd:+7.3f}  "
        f"|  raw: {raw_hex}"
    )

def print_crc_error(rx_crc: int, calc_crc: int, raw_hex: str):
    print(
        f"\033[31m[CRC]\033[0m "
        f"recibido={rx_crc:#06x}  calculado={calc_crc:#06x}  "
        f"|  raw: {raw_hex}"
    )

def print_raw(packet: bytes, label: str):
    """Vuelca el paquete en hex + intenta decodificar floats para debug."""
    hexstr = packet.hex(" ")
    floats = []
    if len(packet) >= 2 + 5*4:
        try:
            floats = list(struct.unpack_from('<5f', packet, 2))
        except:
            pass
    print(f"\033[33m[{label}]\033[0m {hexstr}  →  {floats}")

# ─── TX manual (opcional, se usa con comando de teclado) ─────────────────────
def send_packet(ser: serial.Serial, vl: float, vr: float):
    payload = struct.pack('<2f', vl, vr)
    crc     = crc16(HEADER + payload)
    packet  = HEADER + payload + struct.pack('<H', crc)
    ser.write(packet)
    ser.flush()
    print(f"\033[34m[TX]\033[0m  VL={vl:.3f}  VR={vr:.3f}  |  raw: {packet.hex(' ')}")

# ─── Hilo de entrada por teclado ─────────────────────────────────────────────
def keyboard_thread(ser: serial.Serial, stop_event: threading.Event):
    """Permite enviar comandos a la STM32 escribiendo 'vl vr' en consola."""
    print("\n  ┌─────────────────────────────────────────────┐")
    print(  "  │  Comandos de teclado:                       │")
    print(  "  │    <vl> <vr>   → enviar velocidades          │")
    print(  "  │    s           → parar motores (0 0)         │")
    print(  "  │    q           → salir                       │")
    print(  "  │    h           → mostrar esta ayuda          │")
    print(  "  └─────────────────────────────────────────────┘\n")

    while not stop_event.is_set():
        try:
            cmd = input().strip().lower()
            if not cmd:
                continue
            if cmd == 'q':
                print("[KB] Saliendo...")
                stop_event.set()
                break
            elif cmd == 's':
                send_packet(ser, 0.0, 0.0)
            elif cmd == 'h':
                print("  vl vr → velocidades | s → stop | q → salir")
            else:
                parts = cmd.split()
                if len(parts) == 2:
                    vl = float(parts[0])
                    vr = float(parts[1])
                    send_packet(ser, vl, vr)
                else:
                    print("[KB] Formato: <vl> <vr>  (ej: 1.5 -1.5)")
        except (EOFError, KeyboardInterrupt):
            stop_event.set()
            break
        except ValueError:
            print("[KB] Error: valores numéricos inválidos")
        except Exception as e:
            print(f"[KB] Error: {e}")

# ─── Main ────────────────────────────────────────────────────────────────────
def main():
    print("=" * 72)
    print("  DEBUG UART — STM32 ↔ Radxa")
    print(f"  Puerto: {PORT} @ {BAUDRATE} baud")
    print(f"  RX packet: {RX_PACKET_SIZE} bytes  |  TX packet: {TX_PACKET_SIZE} bytes")
    print(f"  Header: {HEADER.hex(' ')}")
    print("=" * 72)

    # Abrir puerto
    try:
        ser = serial.Serial(PORT, BAUDRATE, timeout=TIMEOUT)
        print(f"[INIT] Puerto {PORT} abierto correctamente\n")
    except Exception as e:
        print(f"[ERROR] No se pudo abrir {PORT}: {e}")
        return

    # Hilo de teclado para enviar comandos
    stop_event = threading.Event()
    kb_thread = threading.Thread(
        target=keyboard_thread, args=(ser, stop_event), daemon=True
    )
    kb_thread.start()

    # ─── Bucle RX ────────────────────────────────────────────────────────
    buf = b""
    t_start = time.monotonic()

    try:
        while not stop_event.is_set():
            try:
                waiting = ser.in_waiting
                if waiting:
                    chunk = ser.read(waiting)
                    buf += chunk
                    stats["bytes_read"] += len(chunk)
                else:
                    time.sleep(0.002)
                    continue

                # Consumir todos los paquetes completos en el buffer
                while True:
                    idx = buf.find(HEADER)
                    if idx == -1:
                        # Si el buffer crece mucho sin header, volcarlo como basura
                        if len(buf) > 256:
                            print(f"[WARN] {len(buf)} bytes sin header, descartando...")
                            print_raw(buf[:64], "RAW")
                            buf = b""
                            stats["header_not_found"] += 1
                        break

                    if idx > 0:
                        # Bytes antes del header → posible basura
                        garbage = buf[:idx]
                        if len(garbage) >= 2:
                            print(f"[WARN] {len(garbage)} bytes basura antes del header: {garbage.hex(' ')}")
                        buf = buf[idx:]

                    if len(buf) < RX_PACKET_SIZE:
                        break  # paquete incompleto, esperar más bytes

                    packet = buf[:RX_PACKET_SIZE]
                    buf    = buf[RX_PACKET_SIZE:]

                    # Validar CRC
                    rx_crc   = struct.unpack_from('<H', packet, RX_PACKET_SIZE - 2)[0]
                    calc_crc = crc16(packet[:RX_PACKET_SIZE - 2])

                    if rx_crc != calc_crc:
                        stats["crc_errors"] += 1
                        print_crc_error(rx_crc, calc_crc, packet.hex(" "))
                        continue

                    # Decodificar payload
                    yaw, pitch, roll, left_spd, right_spd = \
                        struct.unpack_from('<5f', packet, 2)

                    stats["packets_ok"] += 1
                    print_packet(yaw, pitch, roll, left_spd, right_spd, packet.hex(" "))

            except serial.SerialException as e:
                print(f"[ERROR] Puerto serial: {e}")
                break
            except Exception as e:
                print(f"[ERROR] Bucle RX: {e}")
                time.sleep(0.01)

    except KeyboardInterrupt:
        print("\n[STOP] Ctrl+C recibido")

    finally:
        stop_event.set()
        ser.close()

        # ─── Estadísticas finales ───────────────────────────────────────
        elapsed = time.monotonic() - t_start
        print("\n" + "=" * 72)
        print("  ESTADÍSTICAS")
        print("=" * 72)
        print(f"  Tiempo total:       {elapsed:.1f} s")
        print(f"  Bytes leídos:       {stats['bytes_read']}")
        print(f"  Paquetes OK:        {stats['packets_ok']}")
        print(f"  Errores CRC:        {stats['crc_errors']}")
        print(f"  Headers perdidos:   {stats['header_not_found']}")
        if elapsed > 0:
            print(f"  Paquetes/s:         {stats['packets_ok']/elapsed:.1f}")
            print(f"  Bytes/s:            {stats['bytes_read']/elapsed:.1f}")
        print("=" * 72)


if __name__ == "__main__":
    main()
