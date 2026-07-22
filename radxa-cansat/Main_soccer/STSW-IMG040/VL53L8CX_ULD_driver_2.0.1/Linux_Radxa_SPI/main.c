/**
 * main.c
 *
 * Bring-up + primer ranging real del VL53L8CX sobre SPI en la Radxa CM4.
 *
 * Etapas cubiertas en este archivo (ver conversación de diseño):
 *   1) Platform_Init()      -> abrir SPI + retener GPIO LPn
 *   2) Reset_Sensor()       -> LPn low->high, habilitar comunicación
 *   3) vl53l8cx_is_alive()  -> confirmar que el chip responde (ya validado)
 *   4) vl53l8cx_init()      -> cargar firmware interno del sensor (ULD)
 *   5) start_ranging() + loop de check_data_ready()/get_ranging_data()
 *      -> siguiendo la secuencia oficial de Examples/Example_1_ranging_basic.c
 *   6) stop_ranging() + Platform_Close()
 *
 * IMPORTANTE (verifica esto antes de compilar):
 *   - El nombre exacto del header de la API del ULD puede variar entre
 *     versiones ("vl53l8cx_api.h" es lo habitual). Ajusta el #include
 *     de abajo si tu paquete usa otro nombre/ruta.
 *   - El struct "VL53L8CX_Configuration" y las funciones
 *     "vl53l8cx_is_alive/init/start_ranging/check_data_ready/
 *     get_ranging_data/stop_ranging" son los nombres estándar del ULD de
 *     ST para VL53L5CX/VL53L8CX. Si tu versión difiere, ajusta aquí, no
 *     en el ULD.
 *   - "Dev.platform.address" (usado en el ejemplo oficial de ST para I2C)
 *     NO se toca aquí a propósito: nuestro platform.c (SPI) nunca lee ese
 *     campo, solo existe en el struct porque vl53l8cx_api.c lo referencia
 *     en vl53l8cx_set_i2c_address(), que no llamamos.
 *
 * Ajusta también las constantes de pines más abajo (SPI_DEVICE,
 * GPIO_CHIP_LPN, GPIO_LINE_LPN) a lo que confirmaste con gpiofind en tu
 * Radxa CM4 (LPn = pin físico 29 -> gpiochip3, línea 2, según lo que
 * reportaste).
 */

#include <stdio.h>

#include "platform.h"
#include "vl53l8cx_api.h"   /* AJUSTAR si el nombre/ruta real difiere */

/* ---- Configuración de hardware: AJUSTAR a tu cableado real ---- */
#define SPI_DEVICE      "/dev/spidev1.0"
#define GPIO_CHIP_LPN   "gpiochip3"   /* resultado de: gpiofind PIN_29 */
#define GPIO_LINE_LPN   2u             /* resultado de: gpiofind PIN_29 */

/* Número de frames a capturar en esta prueba (igual que Example_1 de ST) */
#define NUM_FRAMES      10u

/* Resolución por defecto del ULD es 4x4 = 16 zonas (no la cambiamos aquí,
 * el ejemplo oficial de ST tampoco la cambia en Example_1). Si más
 * adelante llamas a vl53l8cx_set_resolution(VL53L8CX_RESOLUTION_8X8),
 * ajusta este número a 64. */
#define NUM_ZONES       16u

static void print_diagnostic_checklist(void)
{
    printf("\nVL53L8CX NO detectado / fallo. Revisa en este orden:\n");
    printf("  1) Alimentacion VIN real en el sensor\n");
    printf("  2) LPn realmente en alto en el PIN del sensor (no solo en el GPIO de la Radxa)\n");
    printf("  3) Cableado MOSI/MISO/SCK/CS\n");
    printf("  4) SPI_I2C_N realmente a 3.3V en el conector del sensor\n");
}

int main(void)
{
    VL53L8CX_Configuration Dev; /* struct principal del ULD; contiene .platform */
    VL53L8CX_ResultsData   Results;
    uint8_t status;
    uint8_t is_alive = 0;
    uint8_t is_ready = 0;
    uint8_t frame_count = 0;
    uint32_t i;

    printf("=== VL53L8CX - Bring-up + Ranging SPI Linux/Radxa ===\n");

    /* ---- 1) Platform_Init ---- */
    printf("Initializing platform...\n");
    status = VL53L8CX_Platform_Init(
                &Dev.platform,
                SPI_DEVICE,
                GPIO_CHIP_LPN,
                GPIO_LINE_LPN);
    if (status != 0) {
        fprintf(stderr, "ERROR: Platform_Init falló (status=%u)\n", status);
        return 1;
    }

    /* ---- 2) Reset / habilitar sensor vía LPn ---- */
    printf("Resetting sensor (LPn low->high)...\n");
    status = VL53L8CX_Reset_Sensor(&Dev.platform);
    if (status != 0) {
        fprintf(stderr, "ERROR: Reset_Sensor falló (status=%u)\n", status);
        VL53L8CX_Platform_Close(&Dev.platform);
        return 1;
    }

    /* ---- 3) is_alive ---- */
    printf("Checking sensor...\n");
    status = vl53l8cx_is_alive(&Dev, &is_alive);
    printf("status = %u, alive = %u\n", status, is_alive);

    if (status != 0 || is_alive != 1) {
        print_diagnostic_checklist();
        VL53L8CX_Platform_Close(&Dev.platform);
        return 1;
    }
    printf("VL53L8CX detected!\n\n");

    /* ---- 4) init: carga el firmware interno del sensor.
     * Toma unos cientos de ms, es normal que tarde. */
    printf("Loading VL53L8CX firmware (vl53l8cx_init)...\n");
    status = vl53l8cx_init(&Dev);
    if (status != 0) {
        fprintf(stderr, "ERROR: vl53l8cx_init falló (status=%u)\n", status);
        VL53L8CX_Platform_Close(&Dev.platform);
        return 1;
    }
    printf("VL53L8CX ULD ready! (Version: %s)\n\n", VL53L8CX_API_REVISION);

    /* ---- 5) Ranging: captura NUM_FRAMES frames, igual que Example_1 ---- */
    status = vl53l8cx_start_ranging(&Dev);
    if (status != 0) {
        fprintf(stderr, "ERROR: vl53l8cx_start_ranging falló (status=%u)\n", status);
        VL53L8CX_Platform_Close(&Dev.platform);
        return 1;
    }

    while (frame_count < NUM_FRAMES) {
        /* Polling. Alternativa futura: usar INT (pin 31) en vez de sondeo. */
        status = vl53l8cx_check_data_ready(&Dev, &is_ready);
        if (status != 0) {
            fprintf(stderr, "ERROR: check_data_ready falló (status=%u)\n", status);
            break;
        }

        if (is_ready) {
            status = vl53l8cx_get_ranging_data(&Dev, &Results);
            if (status != 0) {
                fprintf(stderr, "ERROR: get_ranging_data falló (status=%u)\n", status);
                break;
            }

            printf("Frame no: %3u\n", Dev.streamcount);
            for (i = 0; i < NUM_ZONES; i++) {
                printf("  Zona %2u | status=%3u | distancia=%4d mm\n",
                       (unsigned)i,
                       Results.target_status[VL53L8CX_NB_TARGET_PER_ZONE * i],
                       Results.distance_mm[VL53L8CX_NB_TARGET_PER_ZONE * i]);
            }
            printf("\n");
            frame_count++;
        }

        /* Evitar polling excesivo, misma pauta que el ejemplo oficial */
        VL53L8CX_WaitMs(&(Dev.platform), 5);
    }

    /* ---- 6) Cierre ---- */
    status = vl53l8cx_stop_ranging(&Dev);
    if (status != 0) {
        fprintf(stderr, "WARN: vl53l8cx_stop_ranging status=%u\n", status);
    }

    VL53L8CX_Platform_Close(&Dev.platform);

    printf("Fin de la prueba de ranging.\n");
    return 0;
}
