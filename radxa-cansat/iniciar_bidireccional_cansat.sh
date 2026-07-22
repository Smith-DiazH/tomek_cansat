#!/bin/bash

# =====================================================================
# SCRIPT COMPLETO MULTIPLEXOR BIDIRECCIONAL  iniciar_bidireccional_cansat.sh
# =====================================================================

PORT_LORA="/dev/ttyS4"
PORT_GPS="/dev/ttyS2"
PORT_STM32="/dev/ttyS7" # uart7_m0 asignado para el IMU

# Rutas absolutas del entorno y proyecto en la subcarpeta
DIR_PROYECTO="/home/radxa/Documents/yolo_npu/radxa-cansat"
DIR_VENV="/home/radxa/Documents/yolo_npu/venv"

limpiar_sistema_operativo() {
    echo -e "\n[Bash] Cerrando transceptor y liberando canales de hardware..."

    # Inyección de quiebres eléctricos para limpiar líneas colgadas (UARTs)
    sudo tcsendbreak $PORT_LORA 2>/dev/null
    sudo tcsendbreak $PORT_GPS 2>/dev/null
    sudo tcsendbreak $PORT_STM32 2>/dev/null

    # Reset de bajo nivel en el kernel de Linux para los descriptores seriales
    sudo stty -F $PORT_LORA sane
    sudo stty -F $PORT_GPS sane
    sudo stty -F $PORT_STM32 sane

    # Estabilizar configuración base con políticas HUPCL (Evita bloqueos de recursos)
    sudo stty -F $PORT_LORA 115200 cs8 -parenb -cstopb -echo hupcl
    sudo stty -F $PORT_GPS 9600 cs8 -parenb -cstopb -echo hupcl
    sudo stty -F $PORT_STM32 115200 cs8 -parenb -cstopb -echo hupcl

    echo "[Bash] Los 3 puertos UART han quedado en estado limpio y desbloqueados."
    exit 0
}

# Capturar combinación Ctrl+C para interrumpir en cascada y limpiar hardware
trap limpiar_sistema_operativo SIGINT

echo "[1/3] Moviéndose a la subcarpeta de desarrollo CanSat..."
cd "$DIR_PROYECTO" || { echo "[Error] No se encontró la ruta especificada"; exit 1; }

echo "[2/3] Configurando políticas de energía HUPCL en UART4, UART2 y UART7..."
# Forzar asignación de velocidades y modos a nivel kernel para evitar "Permission Denied"
sudo stty -F $PORT_LORA 115200 cs8 -parenb -cstopb -echo hupcl
sudo stty -F $PORT_GPS 9600 cs8 -parenb -cstopb -echo hupcl
sudo stty -F $PORT_STM32 115200 cs8 -parenb -cstopb -echo hupcl

echo "[3/3] Lanzando script multiplexor binario con entorno virtual (Sudo Python)..."
echo "------------------------------------------------------------------------"
# Invocación directa del nuevo core en Python
"$DIR_VENV/bin/python" sender_receiver_lora.py

# En caso de que el script principal finalice por su cuenta, limpiar de inmediato
limpiar_sistema_operativo
