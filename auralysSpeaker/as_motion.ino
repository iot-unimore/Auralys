/* ============================================================================= */
/* MOTION                                                                        */
/* ============================================================================= */


void motionSetup()
{
    sensMotionEnabled = false;
    sensMotion.enableDefault();
    sensMotionEnabled = true;
}

void motionLoop()
{
    int16_t x, y, z;

    sensMotion.readAccel(&x, &y, &z);

    /* update main variables */
    acc_x = x * MOTION_SENSITIVITY_2G * MG_TO_MS2;;
    acc_y = y * MOTION_SENSITIVITY_2G * MG_TO_MS2;;
    acc_z = z * MOTION_SENSITIVITY_2G * MG_TO_MS2;;
}
