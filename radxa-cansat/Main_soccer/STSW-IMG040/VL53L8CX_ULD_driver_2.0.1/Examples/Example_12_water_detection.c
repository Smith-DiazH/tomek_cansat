/*******************************************************************************
* Copyright (c) 2020, STMicroelectronics - All Rights Reserved
*
* This file, part of the VL53L8CX Ultra Lite Driver,
* is licensed under terms that can be found in the LICENSE file
* in the root directory of this software component.
* If no LICENSE file comes with this software, it is provided AS-IS.
*
*******************************************************************************/

/***********************************/
/*   vl53L8CX ULD basic example    */
/***********************************/
/*
 * This example is a variation on the basic range. It initializes the vl53L8CX ULD, and starts
 * a ranging frames forever.
 *
 * Instead of printing an array of values, it sends the raw data ot the liquid detect funciton.
 * Liquid detect returns the height of the liquid provided the Sensor_height is given.
 *
 *
 * By default, ULD is configured to have the following settings :
 * - Resolution 4x4 - but here we change it to 8x8
 * - Ranging period 1Hz
 *
 * In this example, we also suppose that the number of target per zone is
 * set to 1 , and all output are enabled (see file platform.h).
 */

#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include "vl53L8cx_api.h"

int liquid_detect(
		VL53L8CX_ResultsData *range, int Sensor_height, int *liquid_height)
{
	/* center zone locations:
	 *         19,20
	 *      26,27,28,29
	 *      34,35,36,37
	 *         43,44
	 */

	int search_zones[12] = {27,28,35,36,19,20,26,29,34,37,43,44}; //center zones
	int i, idx, status, distance, r_signal, targets=0;
	int max_signal = 0;
	for (i=0; i<12; i++){
		idx = search_zones[i];
		status = range->target_status[VL53L8CX_NB_TARGET_PER_ZONE*idx];
		distance = range->distance_mm[VL53L8CX_NB_TARGET_PER_ZONE*idx];
		r_signal = range->signal_per_spad[VL53L8CX_NB_TARGET_PER_ZONE*idx];
		targets = range->nb_target_detected[VL53L8CX_NB_TARGET_PER_ZONE*idx];
		if(targets>0 && (status == 5 || status == 6 || status == 9))
		{
			if((r_signal ) > max_signal) {
				max_signal = r_signal;
				*liquid_height = Sensor_height - distance;
			}
		}
	}
	return 0;
}

int example12_water_detect(void)
{

	/*********************************/
	/*   vl53L8CX ranging variables  */
	/*********************************/

	uint8_t 				status, loop, isAlive, isReady;
	VL53L8CX_Configuration 	Dev;			/* Sensor configuration */
	VL53L8CX_ResultsData 	Results;		/* Results data from vl53L8CX */

	int liquid_height;

	/*********************************/
	/*      Customer platform        */
	/*********************************/

	/* Fill the platform structure with customer's implementation. For this
	 * example, only the I2C address is used.
	 */
	Dev.platform.address = VL53L8CX_DEFAULT_I2C_ADDRESS;

	/* (Optional) Reset sensor toggling PINs (see platform, not in API) */
	//Reset_Sensor(&(Dev.platform));

	/* (Optional) Set a new I2C address if the wanted address is different
	 * from the default one (filled with 0x20 for this example).
	 */
	//status = vl53L8cx_set_i2c_address(&Dev, 0x20);


	/*********************************/
	/*   Power on sensor and init    */
	/*********************************/

	/* (Optional) Check if there is a vl53L8CX sensor connected */

	status = vl53l8cx_is_alive(&Dev, &isAlive);
	if(!isAlive || status)
	{
		printf("vl53L8CX not detected at requested address\n");
		return status;
	}

	/* (Mandatory) Init vl53L8CX sensor */
	status = vl53l8cx_init(&Dev);
	if(status)
	{
		printf("vl53L8CX ULD Loading failed\n");
		return status;
	}

	printf("vl53L8CX ULD ready ! (Version : %s)\n",
			VL53L8CX_API_REVISION);

	status = vl53l8cx_set_ranging_frequency_hz(&Dev, 2);				// Set 2Hz ranging frequency
	status = vl53l8cx_set_ranging_mode(&Dev, VL53L8CX_RANGING_MODE_CONTINUOUS);  // Set mode continuous
	status = vl53l8cx_set_resolution(&Dev,VL53L8CX_RESOLUTION_8X8);

	/*********************************/
	/*         Ranging loop          */
	/*********************************/

	status = vl53l8cx_start_ranging(&Dev);

	loop = 0;
	while(1)  // loop foreveer
	{
		/* Use polling function to know when a new measurement is ready.
		 * Another way can be to wait for HW interrupt raised on PIN A3
		 * (GPIO 1) when a new measurement is ready */

		status = vl53l8cx_check_data_ready(&Dev, &isReady);

		if(isReady)
		{
			vl53l8cx_get_ranging_data(&Dev, &Results);

			liquid_detect(&Results, 216, &liquid_height);
			/* As the sensor is set in 4x4 mode by default, we have a total 
			 * of 16 zones to print. For this example, only the data of first zone are 
			 * print */

			if (liquid_height < 0) {
				printf("The sensor height is higher than 30cm.\n");
			} else
				printf("Assuming a sensor height of 21.6cm, the liquid level is %d.%d cm high.\n", liquid_height/10, liquid_height%10);
		}

		loop++;
		HAL_Delay(100); // since the inter-measurement period is 500ms
	}

	status = vl53l8cx_stop_ranging(&Dev);
	printf("End of ULD demo\n");
	return status;
}


