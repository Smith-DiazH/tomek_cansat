/**
 * platform.h
 *
 * Capa de plataforma Linux (Radxa CM4, SPI + libgpiod) para el driver
 * VL53L8CX_ULD de STMicroelectronics.
 *
 * IMPORTANTE:
 * El nombre del struct VL53L8CX_Platform y las firmas de las funciones
 * VL53L8CX_RdByte / VL53L8CX_WrByte / VL53L8CX_WrMulti / VL53L8CX_RdMulti /
 * VL53L8CX_SwapBuffer / VL53L8CX_WaitMs deben coincidir EXACTAMENTE con lo
 * que declara el platform.h original dentro de tu copia de
 * VL53L8CX_ULD_API/ (o de la carpeta Platform/ de referencia de ST).
 *
 * Este archivo fue escrito sin tener a la vista tu versión exacta del ULD,
 * así que antes de compilar: abre el platform.h oficial de tu paquete y
 * confirma que estos prototipos calzan. Si hay diferencias, ajusta aquí,
 * no en el ULD.
 */

#ifndef PLATFORM_H_
#define PLATFORM_H_

#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/* -------------------------------------------------------------------------
 * VL53L8CX_NB_TARGET_PER_ZONE: macro de configuración que el propio
 * vl53l8cx_api.h requiere que el usuario defina en su platform.h (no tiene
 * valor por defecto dentro del ULD, a diferencia de las macros
 * VL53L8CX_DISABLE_*, que sí tienen fallback). Controla el tamaño de varios
 * arrays de resultados (distance_mm, target_status, etc.).
 *
 * Valor 1U = un solo target por zona. Es el valor usado en TODOS los
 * ejemplos oficiales de ST (STM32 SPI, STM32 I2C, Platform/platform.h de
 * referencia), y es el caso simple recomendado para empezar. Si más
 * adelante necesitas multi-target por zona, cambia este valor (ver
 * Examples/Example_5_multiple_targets_per_zone.c del paquete ST).
 * ---------------------------------------------------------------------- */
#define VL53L8CX_NB_TARGET_PER_ZONE 1U

/* -------------------------------------------------------------------------
 * Contexto de plataforma que el ULD pasa a cada función de comunicación.
 * Solo SPI: no guardamos dirección I2C porque no la usamos.
 * ---------------------------------------------------------------------- */
typedef struct
{
    int      spi_fd;         /* fd devuelto por open("/dev/spidevX.Y")      */
    uint32_t speed_hz;        /* velocidad de reloj SPI, ej. 1000000 (1MHz)  */
    uint8_t  mode;             /* SPI_MODE_3 obligatorio para el VL53L8CX     */
    uint8_t  bits_per_word;    /* normalmente 8                                */

    /* Requerido por vl53l8cx_api.c (vl53l8cx_set_i2c_address()), aunque
     * nosotros usamos SPI y nunca lo llenamos con un valor útil. El campo
     * debe existir igual porque vl53l8cx_api.c es una sola unidad de
     * compilación compartida entre I2C y SPI. Confirmado por grep que
     * NINGÚN otro campo del platform.h de referencia de ST (como
     * spi_comm_buffer) se usa realmente en los .c de este ULD, así que no
     * lo agregamos para no reservar memoria de más sin necesidad. */
    uint16_t address;
} VL53L8CX_Platform;

/* -------------------------------------------------------------------------
 * Funciones requeridas por el ULD (mismos nombres/firmas que el ejemplo
 * STM32 que ya tienes, adaptadas a Linux/spidev).
 * ---------------------------------------------------------------------- */
uint8_t VL53L8CX_RdByte(
        VL53L8CX_Platform *p_platform,
        uint16_t RegisterAdress,
        uint8_t *p_value);

uint8_t VL53L8CX_WrByte(
        VL53L8CX_Platform *p_platform,
        uint16_t RegisterAdress,
        uint8_t value);

uint8_t VL53L8CX_WrMulti(
        VL53L8CX_Platform *p_platform,
        uint16_t RegisterAdress,
        uint8_t *p_values,
        uint32_t size);

uint8_t VL53L8CX_RdMulti(
        VL53L8CX_Platform *p_platform,
        uint16_t RegisterAdress,
        uint8_t *p_values,
        uint32_t size);

void VL53L8CX_SwapBuffer(
        uint8_t *buffer,
        uint16_t size);

uint8_t VL53L8CX_WaitMs(
        VL53L8CX_Platform *p_platform,
        uint32_t TimeMs);

/* -------------------------------------------------------------------------
 * Funciones propias de nuestro puerto Linux/Radxa (NO son parte del ULD
 * de ST, las inventamos nosotros para reemplazar lo que en STM32 hacía
 * el HAL + CubeMX).
 * ---------------------------------------------------------------------- */

/**
 * Abre /dev/spidevX.Y, configura modo/velocidad/bits, y solicita (requests)
 * la línea GPIO de LPn dejándola RETENIDA ABIERTA (no se abre y cierra en
 * cada toggle). LPn queda inicialmente en BAJO; usa
 * VL53L8CX_Reset_Sensor() para subirla y habilitar el sensor.
 *
 * gpio_chip_lpn: nombre del chip, ej. "gpiochip3" (según gpiofind del pin29)
 * gpio_line_lpn: offset de línea dentro de ese chip, ej. 2
 *
 * Retorna 0 en éxito, distinto de 0 en error.
 */
uint8_t VL53L8CX_Platform_Init(
        VL53L8CX_Platform *p_platform,
        const char *spi_device,
        const char *gpio_chip_lpn,
        unsigned int gpio_line_lpn);

/**
 * Secuencia de habilitación/reset del sensor vía LPn:
 * LPn bajo -> delay -> LPn alto -> delay.
 * LPn queda en ALTO (sensor habilitado) al retornar.
 * La línea GPIO se mantiene abierta durante todo el ciclo de vida del
 * programa; esta función NO abre ni cierra el chip GPIO.
 */
uint8_t VL53L8CX_Reset_Sensor(VL53L8CX_Platform *p_platform);

/**
 * Libera el fd de SPI y la línea GPIO de LPn. Llamar una sola vez, al
 * finalizar el programa.
 */
void VL53L8CX_Platform_Close(VL53L8CX_Platform *p_platform);

#ifdef __cplusplus
}
#endif

#endif /* PLATFORM_H_ */
