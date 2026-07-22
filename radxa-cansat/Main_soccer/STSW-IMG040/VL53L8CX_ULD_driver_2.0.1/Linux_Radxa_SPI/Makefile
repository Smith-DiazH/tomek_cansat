# Makefile - VL53L8CX bring-up sobre SPI, Radxa CM4 / Linux
#
# Estructura esperada (ajusta ULD_DIR si tu carpeta tiene otro nombre):
#
#   VL53L8CX_ULD_driver_2.0.1/
#   +-- VL53L8CX_ULD_API/     <- código oficial de ST (no lo tocamos)
#   +-- Linux_Radxa_SPI/      <- este Makefile vive aquí
#
# No copiamos ningún archivo del ULD: lo incluimos por ruta (-I) y
# compilamos sus .c directamente desde su ubicación original.

CC      := gcc
CFLAGS  := -Wall -Wextra -O2 -std=gnu11
LDLIBS  := -lgpiod

# Carpeta del ULD oficial de ST, relativa a este Makefile.
# AJUSTAR si tu paquete descargado usa otro nombre de carpeta.
ULD_DIR := ../VL53L8CX_ULD_API

# Autodetección de includes y fuentes del ULD.
# Si tu ULD separa headers/fuentes en subcarpetas (p.ej. inc/ y src/),
# esto los encuentra igual gracias a -r en find; si tu estructura es
# distinta, ajusta ULD_INC_DIRS / ULD_SRCS a mano.
ULD_INC_DIRS := $(shell find $(ULD_DIR) -type d)
ULD_SRCS     := $(shell find $(ULD_DIR) -name '*.c')

INCLUDES := -I. $(addprefix -I,$(ULD_INC_DIRS))

BUILD_DIR := build
TARGET    := vl53l8cx_test

LOCAL_SRCS := main.c platform.c
ALL_SRCS   := $(LOCAL_SRCS) $(ULD_SRCS)

OBJS := $(addprefix $(BUILD_DIR)/,$(notdir $(ALL_SRCS:.c=.o)))

# vpath para que make encuentre los .c del ULD aunque estén en otras carpetas
vpath %.c . $(ULD_DIR) $(sort $(dir $(ULD_SRCS)))

.PHONY: all clean printvars

all: $(BUILD_DIR) $(TARGET)

$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

$(BUILD_DIR)/%.o: %.c
	$(CC) $(CFLAGS) $(INCLUDES) -c $< -o $@

$(TARGET): $(OBJS)
	$(CC) $(CFLAGS) $(OBJS) -o $@ $(LDLIBS)

clean:
	rm -rf $(BUILD_DIR) $(TARGET)

# Util para depurar el Makefile si algo no compila por rutas:
printvars:
	@echo "ULD_INC_DIRS = $(ULD_INC_DIRS)"
	@echo "ULD_SRCS     = $(ULD_SRCS)"
	@echo "ALL_SRCS     = $(ALL_SRCS)"
	@echo "OBJS         = $(OBJS)"
