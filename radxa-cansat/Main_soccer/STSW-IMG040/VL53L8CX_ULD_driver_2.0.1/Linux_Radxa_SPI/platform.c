/**
 * platform.c
 *
 * Implementación Linux (Radxa CM4) de la capa de plataforma del ULD
 * VL53L8CX. Traduce las llamadas del driver (RdMulti/WrMulti/WaitMs/...)
 * a operaciones sobre /dev/spidevX.Y (vía ioctl SPI_IOC_MESSAGE) y sobre
 * la línea GPIO de LPn (vía libgpiod).
 *
 * Protocolo SPI del VL53L8CX (confirmado en el datasheet oficial de ST):
 *   - SPI Mode 3 (CPOL=1, CPHA=1)
 *   - Bit 15 de la dirección de 16 bits: 1 = escritura, 0 = lectura
 *   - Sin CRC, sin bytes dummy
 *   - En una lectura: primero se transmiten 2 bytes de dirección con NCS
 *     bajo, y SIN soltar NCS se reciben los bytes de datos. Por eso la
 *     transacción de lectura se hace como UNA sola llamada ioctl con dos
 *     "spi_ioc_transfer" encadenados (cs_change=0 en el primero) para que
 *     el driver de spidev mantenga NCS activo entre ambos sub-transfers.
 */

#include "platform.h"

#include <stdio.h>
#include <string.h>
#include <fcntl.h>
#include <unistd.h>
#include <errno.h>
#include <time.h>

#include <sys/ioctl.h>
#include <linux/spi/spidev.h>

#include <gpiod.h>

/* IMPORTANTE: en el ejemplo STM32 de referencia este valor es 4096, pero
 * ahí no aplica porque HAL_SPI_Transmit/Receive no tienen este límite.
 * En Linux, el driver spidev limita cada transferencia individual a
 * "bufsiz" (parámetro de módulo del kernel). Confirmado en la Radxa CM4
 * con:
 *   cat /sys/module/spidev/parameters/bufsiz   ->  4096
 *
 * En WrMulti, una sola transferencia lleva 2 bytes de dirección + los
 * datos, así que data_size + 2 debe ser <= bufsiz. Se deja margen (4092
 * en vez de 4094 exactos) para no rozar el límite justo. Si en otra
 * plataforma "bufsiz" es distinto, ajusta este valor acorde (verifica
 * primero con el comando de arriba, no asumas 4096). */
#define VL53L8CX_COMMS_CHUNK_SIZE 4092

#define SPI_WRITE_MASK(x) (uint16_t)((x) | 0x8000)
#define SPI_READ_MASK(x)  (uint16_t)((x) & ~0x8000)

/* -------------------------------------------------------------------------
 * Estado de la línea LPn. Se mantiene como estático a nivel de archivo
 * -a propósito- en vez de guardarlo dentro de VL53L8CX_Platform, según lo
 * que decidimos: el ULD no necesita saber nada de GPIO, solo nuestra capa
 * de plataforma lo usa.
 *
 * IMPORTANTE: chip y línea se abren UNA sola vez en Platform_Init() y se
 * mantienen retenidos (gpiod_line_request_output) durante toda la vida del
 * programa. Nunca se liberan entre un toggle y otro: liberar la línea
 * puede hacer que el pinctrl del SoC la devuelva a alta impedancia y el
 * sensor pierda la habilitación de comunicación sin que el código lo note.
 * ---------------------------------------------------------------------- */
static struct gpiod_chip *s_lpn_chip = NULL;
static struct gpiod_line *s_lpn_line = NULL;

static void sleep_ms(unsigned int ms)
{
    struct timespec ts;
    ts.tv_sec  = ms / 1000;
    ts.tv_nsec = (long)(ms % 1000) * 1000000L;
    nanosleep(&ts, NULL);
}

/* ==========================================================================
 * Inicialización de plataforma
 * ======================================================================= */
uint8_t VL53L8CX_Platform_Init(
        VL53L8CX_Platform *p_platform,
        const char *spi_device,
        const char *gpio_chip_lpn,
        unsigned int gpio_line_lpn)
{
    if (p_platform == NULL || spi_device == NULL || gpio_chip_lpn == NULL) {
        return 1;
    }

    /* ---- 1) Abrir /dev/spidevX.Y ---- */
    int fd = open(spi_device, O_RDWR);
    if (fd < 0) {
        fprintf(stderr, "[platform] No se pudo abrir %s: %s\n",
                spi_device, strerror(errno));
        return 1;
    }

    uint8_t  mode          = SPI_MODE_3;   /* CPOL=1, CPHA=1: obligatorio */
    uint8_t  bits_per_word = 8;
    uint32_t speed_hz      = 1000000;      /* 1 MHz para las primeras pruebas */

    if (ioctl(fd, SPI_IOC_WR_MODE, &mode) < 0) {
        fprintf(stderr, "[platform] SPI_IOC_WR_MODE falló: %s\n", strerror(errno));
        close(fd);
        return 1;
    }
    if (ioctl(fd, SPI_IOC_WR_BITS_PER_WORD, &bits_per_word) < 0) {
        fprintf(stderr, "[platform] SPI_IOC_WR_BITS_PER_WORD falló: %s\n", strerror(errno));
        close(fd);
        return 1;
    }
    if (ioctl(fd, SPI_IOC_WR_MAX_SPEED_HZ, &speed_hz) < 0) {
        fprintf(stderr, "[platform] SPI_IOC_WR_MAX_SPEED_HZ falló: %s\n", strerror(errno));
        close(fd);
        return 1;
    }

    p_platform->spi_fd        = fd;
    p_platform->mode          = mode;
    p_platform->bits_per_word = bits_per_word;
    p_platform->speed_hz      = speed_hz;

    /* ---- 2) Solicitar y retener la línea GPIO de LPn ---- */
    s_lpn_chip = gpiod_chip_open_by_name(gpio_chip_lpn);
    if (s_lpn_chip == NULL) {
        fprintf(stderr, "[platform] No se pudo abrir el chip GPIO '%s': %s\n",
                gpio_chip_lpn, strerror(errno));
        close(fd);
        return 1;
    }

    s_lpn_line = gpiod_chip_get_line(s_lpn_chip, gpio_line_lpn);
    if (s_lpn_line == NULL) {
        fprintf(stderr, "[platform] No se pudo obtener la línea %u del chip '%s': %s\n",
                gpio_line_lpn, gpio_chip_lpn, strerror(errno));
        gpiod_chip_close(s_lpn_chip);
        s_lpn_chip = NULL;
        close(fd);
        return 1;
    }

    /* Se solicita como salida, arrancando en BAJO (sensor deshabilitado
     * hasta que llamemos a VL53L8CX_Reset_Sensor()). La línea queda
     * retenida (requested) hasta VL53L8CX_Platform_Close(). */
    if (gpiod_line_request_output(s_lpn_line, "vl53l8cx-lpn", 0) < 0) {
        fprintf(stderr, "[platform] gpiod_line_request_output falló: %s\n",
                strerror(errno));
        gpiod_chip_close(s_lpn_chip);
        s_lpn_chip = NULL;
        s_lpn_line = NULL;
        close(fd);
        return 1;
    }

    printf("[platform] SPI listo (%s, mode=%d, %u Hz), LPn en '%s' línea %u\n",
           spi_device, mode, speed_hz, gpio_chip_lpn, gpio_line_lpn);

    return 0;
}

/* ==========================================================================
 * Reset / habilitación del sensor vía LPn
 * ======================================================================= */
uint8_t VL53L8CX_Reset_Sensor(VL53L8CX_Platform *p_platform)
{
    (void)p_platform; /* no usamos el struct aquí, LPn se maneja aparte */

    if (s_lpn_line == NULL) {
        fprintf(stderr, "[platform] LPn no inicializado, llama antes a Platform_Init()\n");
        return 1;
    }

    /* NOTA: los tiempos de espera aquí son conservadores para las primeras
     * pruebas. Si tienes acceso al procedimiento exacto de reset en
     * UM3109 ("sensor reset management"), ajusta estos delays a lo que
     * ST recomienda oficialmente. */
    if (gpiod_line_set_value(s_lpn_line, 0) < 0) {
        fprintf(stderr, "[platform] No se pudo poner LPn en bajo: %s\n", strerror(errno));
        return 1;
    }
    sleep_ms(10);

    if (gpiod_line_set_value(s_lpn_line, 1) < 0) {
        fprintf(stderr, "[platform] No se pudo poner LPn en alto: %s\n", strerror(errno));
        return 1;
    }
    /* Tiempo de arranque del sensor tras habilitar LPn antes de comunicar */
    sleep_ms(20);

    return 0;
}

/* ==========================================================================
 * Cierre / liberación de recursos
 * ======================================================================= */
void VL53L8CX_Platform_Close(VL53L8CX_Platform *p_platform)
{
    if (s_lpn_line != NULL) {
        gpiod_line_release(s_lpn_line);
        s_lpn_line = NULL;
    }
    if (s_lpn_chip != NULL) {
        gpiod_chip_close(s_lpn_chip);
        s_lpn_chip = NULL;
    }
    if (p_platform != NULL && p_platform->spi_fd >= 0) {
        close(p_platform->spi_fd);
        p_platform->spi_fd = -1;
    }
}

/* ==========================================================================
 * Escritura multi-byte
 *
 * Formato: [addr_hi | 0x80][addr_lo][data...]  -- todo en UNA transferencia,
 * NCS bajo durante toda la transacción (esto lo maneja spidev
 * automáticamente para una sola llamada ioctl con un solo spi_ioc_transfer).
 * ======================================================================= */
uint8_t VL53L8CX_WrMulti(
        VL53L8CX_Platform *p_platform,
        uint16_t RegisterAdress,
        uint8_t *p_values,
        uint32_t size)
{
    uint8_t status = 0;
    uint32_t position;
    uint32_t data_size;
    uint16_t temp;
    uint8_t data_write[VL53L8CX_COMMS_CHUNK_SIZE + 2];

    for (position = 0; position < size; position += VL53L8CX_COMMS_CHUNK_SIZE)
    {
        if (size > VL53L8CX_COMMS_CHUNK_SIZE) {
            data_size = ((position + VL53L8CX_COMMS_CHUNK_SIZE) > size)
                        ? (size - position)
                        : VL53L8CX_COMMS_CHUNK_SIZE;
        } else {
            data_size = size;
        }

        temp = (uint16_t)(RegisterAdress + position);

        data_write[0] = (uint8_t)(SPI_WRITE_MASK(temp) >> 8);
        data_write[1] = (uint8_t)(SPI_WRITE_MASK(temp) & 0xFF);

        memcpy(&data_write[2], &p_values[position], data_size);

        struct spi_ioc_transfer tr;
        memset(&tr, 0, sizeof(tr));
        tr.tx_buf        = (unsigned long)data_write;
        tr.rx_buf        = 0; /* no nos interesa lo que llega durante la escritura */
        tr.len           = data_size + 2;
        tr.speed_hz      = p_platform->speed_hz;
        tr.bits_per_word = p_platform->bits_per_word;
        tr.cs_change     = 0; /* soltar NCS al terminar esta transferencia */

        if (ioctl(p_platform->spi_fd, SPI_IOC_MESSAGE(1), &tr) < 1) {
            fprintf(stderr, "[platform] WrMulti ioctl falló: %s\n", strerror(errno));
            status = 1;
        }
    }

    return status;
}

/* ==========================================================================
 * Lectura multi-byte
 *
 * Dos sub-transferencias en UNA sola llamada ioctl:
 *   1) enviar 2 bytes de dirección (cs_change=0 => NCS se mantiene activo)
 *   2) recibir 'size' bytes de datos
 * ======================================================================= */
uint8_t VL53L8CX_RdMulti(
        VL53L8CX_Platform *p_platform,
        uint16_t RegisterAdress,
        uint8_t *p_values,
        uint32_t size)
{
    uint8_t status = 0;
    uint32_t position;
    uint32_t data_size;
    uint16_t temp;
    uint8_t addr_bytes[2];

    for (position = 0; position < size; position += VL53L8CX_COMMS_CHUNK_SIZE)
    {
        if (size > VL53L8CX_COMMS_CHUNK_SIZE) {
            data_size = ((position + VL53L8CX_COMMS_CHUNK_SIZE) > size)
                        ? (size - position)
                        : VL53L8CX_COMMS_CHUNK_SIZE;
        } else {
            data_size = size;
        }

        temp = (uint16_t)(RegisterAdress + position);
        addr_bytes[0] = (uint8_t)(SPI_READ_MASK(temp) >> 8);
        addr_bytes[1] = (uint8_t)(SPI_READ_MASK(temp) & 0xFF);

        struct spi_ioc_transfer tr[2];
        memset(tr, 0, sizeof(tr));

        /* Sub-transfer 1: dirección (escritura), NCS se mantiene activo
         * después (cs_change = 0 en spidev significa "no cambiar el
         * estado de CS al terminar este transfer", así queda activo para
         * el siguiente sub-transfer del mismo mensaje). */
        tr[0].tx_buf        = (unsigned long)addr_bytes;
        tr[0].rx_buf        = 0;
        tr[0].len           = 2;
        tr[0].speed_hz      = p_platform->speed_hz;
        tr[0].bits_per_word = p_platform->bits_per_word;
        tr[0].cs_change     = 0;

        /* Sub-transfer 2: datos (lectura) */
        tr[1].tx_buf        = 0;
        tr[1].rx_buf        = (unsigned long)(p_values + position);
        tr[1].len           = data_size;
        tr[1].speed_hz      = p_platform->speed_hz;
        tr[1].bits_per_word = p_platform->bits_per_word;
        tr[1].cs_change     = 0;

        if (ioctl(p_platform->spi_fd, SPI_IOC_MESSAGE(2), tr) < 1) {
            fprintf(stderr, "[platform] RdMulti ioctl falló: %s\n", strerror(errno));
            status = 1;
        }
    }

    return status;
}

/* ==========================================================================
 * Byte único (se apoyan en las versiones multi)
 * ======================================================================= */
uint8_t VL53L8CX_RdByte(
        VL53L8CX_Platform *p_platform,
        uint16_t RegisterAdress,
        uint8_t *p_value)
{
    return VL53L8CX_RdMulti(p_platform, RegisterAdress, p_value, 1);
}

uint8_t VL53L8CX_WrByte(
        VL53L8CX_Platform *p_platform,
        uint16_t RegisterAdress,
        uint8_t value)
{
    return VL53L8CX_WrMulti(p_platform, RegisterAdress, &value, 1);
}

/* ==========================================================================
 * Utilidades
 * ======================================================================= */
void VL53L8CX_SwapBuffer(uint8_t *buffer, uint16_t size)
{
    uint32_t i, tmp;

    for (i = 0; i < size; i += 4) {
        tmp = ((uint32_t)buffer[i]     << 24)
            | ((uint32_t)buffer[i + 1] << 16)
            | ((uint32_t)buffer[i + 2] << 8)
            |  (uint32_t)buffer[i + 3];

        memcpy(&buffer[i], &tmp, 4);
    }
}

uint8_t VL53L8CX_WaitMs(VL53L8CX_Platform *p_platform, uint32_t TimeMs)
{
    (void)p_platform;
    sleep_ms(TimeMs);
    return 0;
}
