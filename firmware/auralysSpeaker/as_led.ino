/* ============================================================================= */
/* RGB led                                                                       */
/* ============================================================================= */

inline uint32_t ledRgbGetColor()
{
    return ledRgbColorCurrent;
}

inline void ledRgbToggleColor(uint32_t rgbw_val)
{
    ledRgbSetColor((ledRgbColorOff != ledRgbGetColor()) ? ledRgbColorOff : rgbw_val);
}

inline void ledRgbSetColor(uint32_t rgbw_val)
{
    ledRgbColorPrevious = ledRgbColorCurrent;
#ifdef RGB_BUILTIN
    // neopixelWrite(RGB_BUILTIN, (rgbw_val >> 24) & 0xFF, (rgbw_val >> 16) & 0xFF, (rgbw_val >> 8) & 0xFF);
    rgbLedWrite(RGB_BUILTIN, (rgbw_val >> 24) & 0xFF, (rgbw_val >> 16) & 0xFF, (rgbw_val >> 8) & 0xFF);
#endif
    ledRgbColorCurrent = rgbw_val;
}

inline void ledRgbBlink(uint32_t rgbw_val, uint16_t delay_ms)
{
    ledRgbSetColor(rgbw_val);
    delay(delay_ms);
    ledRgbSetColor(ledRgbColorOff);
    delay(delay_ms);
}

inline void ledRgbBlinkN(uint32_t rgbw_val, uint16_t delay_ms, uint8_t n)
{
    for( int i = 0; i < n; i++ )
    {
        ledRgbSetColor(rgbw_val);
        delay(delay_ms);
        ledRgbSetColor(ledRgbColorOff);
        delay(delay_ms);
    }
}

void ledRgbBlinkSOS(uint32_t rgbw_val, uint16_t delay_ms)
{

    /* S */
    ledRgbBlinkN(rgbw_val, delay_ms, 3);

    /* O */
    ledRgbBlinkN(rgbw_val, (3 * delay_ms), 3);

    /* S */
    ledRgbBlinkN(rgbw_val, delay_ms, 3);
}

void ledRgbSetup()
{
    // led config was introduced in hw_config version 0.3
    // if((float) (hw_config.hw_descriptor_mjr * 1.0 + hw_config.hw_descriptor_min * .1) > 0.2 )
    // {
    // if( HW_LED_WS2812BC_GRB == hw_config.hw_led_type_rgb )
    // {
    // LOG_MSGLN("SWITCH LED!");
    // ledRgbColorRed = LED_GRB_RED;
    // ledRgbColorGreen = LED_GRB_GREEN;
    // ledRgbColorBlue = LED_GRB_BLUE;
    // ledRgbColorViolet = LED_GRB_VIOLET;
    // ledRgbColorYellow = LED_GRB_YELLOW;
    // ledRgbColorWhite = LED_RGB_WHITE;
    // ledRgbColorOff = LED_RGB_OFF;
    // }
    // }

    ledRgbSetColor(ledRgbColorOff);
}

void ledRgbLoop()
{
    ///* blink or beep */
    // if((bspBootGraceTimeWindow) && (!(bspInitialized)))
    // {
    // ledRgbBlink(ledRgbColorGreen, LED_DELAY_FAST);
    //// bspPlayBeep(2000, LED_DELAY_FAST);
    // }
}