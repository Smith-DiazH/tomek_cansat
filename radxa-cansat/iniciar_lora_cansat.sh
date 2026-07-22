#!/bin/bash

# =====================================================================
# SCRIPT DEFINITIVO  iniciar_lora_cansat.sh (Modo Superusuario)
# =====================================================================

PORT_LORA="/dev/ttyS4"
PORT_GPS="/dev/ttyS2"

# NUEVA RUTA: Ahora apunta a la subcarpeta
DIR_PROYECTO="/home/radxa/Documents/yolo_npu/radxa-cansat"

# RUTA DEL ENTORNO VIRTUAL (Se mantiene en la carpeta padre)
DIR_VENV="/home/radxa/Documents/yolo_npu/venv"

limpiar_sistema_operativo() {
    echo -e "\n[Bash] Cerrando de forma segura y liberando hardware..."

    # Quiebre de línea eléctrico para limpiar los chips UART del Radxa
    sudo tcsendbreak $PORT_LORA 2>/dev/null
    sudo tcsendbreak $PORT_GPS 2>/dev/null

    # Forzar reset de los drivers seriales en el Kernel de Linux
    sudo stty -F $PORT_LORA sane
    sudo stty -F $PORT_GPS sane

    # Aplicar configuración base limpia asegurando el bit HUPCL para autodestrucción de cuelgues
    sudo stty -F $PORT_LORA 115200 cs8 -parenb -cstopb -echo hupcl
    sudo stty -F $PORT_GPS 9600 cs8 -parenb -cstopb -echo hupcl

    echo "[Bash] UARTs totalmente desbloqueados. El sistema quedó limpio."
    exit 0
}

# Capturar Ctrl+C para ejecutar la limpieza de inmediato
trap limpiar_sistema_operativo SIGINT

echo "[1/3] Moviéndose al directorio del proyecto..."
cd $DIR_PROYECTO || { echo "[Error] No se pudo acceder a la ruta"; exit 1; }

echo "[2/3] Aplicando políticas HUPCL en los puertos con Sudo..."
# Configuramos los puertos con sudo para evitar el "Permission denied"
sudo stty -F $PORT_LORA 115200 cs8 -parenb -cstopb -echo hupcl
sudo stty -F $PORT_GPS 9600 cs8 -parenb -cstopb -echo hupcl

echo "[3/3] Lanzando script con el entorno virtual (Sudo Python)..."
echo "--------------------------------------------------------"
# Forzamos a que Python corra con sudo usando la ruta absoluta del entorno virtual
sudo ${DIR_VENV}/bin/python sender_lora.py

# Limpieza automática si el script cae por su cuenta
limpiar_sistema_operativo
