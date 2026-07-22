#!/usr/bin/env python3
import time
import queue
from robot_state import RobotState
from uart        import STM32UART
from gps         import GPSReader
from lora        import LoRaTransceiver
from logger      import LogWriter
from navigation  import NavigationController   # <- NUEVO
import threading
PORT_STM32 = "/dev/ttyS7"
PORT_GPS   = "/dev/ttyS2"
PORT_LORA  = "/dev/ttyS4"
BAUD_STM32 = 115200
BAUD_GPS   = 9600
BAUD_LORA  = 115200

NAV_HZ     = 20
NAV_PERIOD = 1.0 / NAV_HZ

# <- ELIMINADO: def navigation_step()  ya no se necesita

def main():
    log_q = queue.Queue()
    state = RobotState()
    nav   = NavigationController()             # <- NUEVO
    def _inject_target():
        import time
        time.sleep(3)
        state.update_target(-12.020722, -77.057913)
        print("[TEST] Target inyectado manualmente")
    threading.Thread(target=_inject_target, daemon=True).start()
    # --- Instanciar módulos ---
    logger = LogWriter(log_q=log_q)
    uart   = STM32UART(port=PORT_STM32, baudrate=BAUD_STM32, robot_state=state)
    gps    = GPSReader(robot_state=state, log_q=log_q, port=PORT_GPS, baud=BAUD_GPS)
    lora   = LoRaTransceiver(robot_state=state, log_q=log_q,
                              port=PORT_LORA, baud=BAUD_LORA)

    # --- Arrancar hilos ---
    logger.start()
    gps.start()
    lora.start()

    print("[MAIN] Sistema iniciado. Navegación a 20 Hz. Ctrl+C para salir.\n")

    try:
        while True:
            t0 = time.monotonic()

            # Si llegó un target nuevo por LoRa, resetear el PID  <- NUEVO
            if state.consume_target_flag():
                nav.reset()
                print("[MAIN] Target nuevo  PID reseteado")

            nav.step(state, NAV_PERIOD)        # <- REEMPLAZA navigation_step(state)

            s = state.snapshot()
            print(
                f"YAW={s['yaw']:6.1f}°  "
                f"GPS={'OK' if s['gps_fix'] else '--'}  "
                f"lat={s['latitude']:.5f}  lon={s['longitude']:.5f}  "
                f"VL={s['cmd_vl']:.2f}  VR={s['cmd_vr']:.2f}  "
                f"target={'SET' if s['target_lat'] else 'NONE'}  "
                f"arrived={nav.arrived}"        # <- NUEVO
            )

            elapsed = time.monotonic() - t0
            sleep_t = NAV_PERIOD - elapsed
            if sleep_t > 0:
                time.sleep(sleep_t)

    except KeyboardInterrupt:
        print("\n[MAIN] Apagando...")
    finally:
        uart.stop()
        gps.stop()
        lora.stop()
        logger.solicitar_parada()
        time.sleep(0.5)
        print("[MAIN] Cierre limpio.")

if __name__ == "__main__":
    main()
