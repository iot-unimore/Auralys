/* ============================================================================= */
/* DISPLAY CONTROL */
/* ============================================================================= */
#define LINE_ORIGIN (14)
#define LINE_SIZE (10)

void displaySetup()
{
    char sbuf[64];

    display.begin(SCREEN_I2C_ADDR, true);
    // display.setContrast (0); // dim display

    bspDisplayLogMsgIdx = 0;
    snprintf(bspDisplayLogMsg[0], 20, "                    ");
    snprintf(bspDisplayLogMsg[1], 20, "                    ");

    display.clearDisplay();
    display.display();

    /* show mks config */
    sprintf(sbuf, "SPEED: %d", hw_config.hw_mks_speed);
    displayCtrlLogMsg(sbuf);
    sprintf(sbuf, "ACCEL: %d", hw_config.hw_mks_accel);
    displayCtrlLogMsg(sbuf);
}

void displayLoop()
{
    char sbuf[64];
    struct tm timeinfo;

    if( bspDisplayCtrlFullscreen )
    {
        display.clearDisplay();

        snprintf(sbuf, 63, bspDisplayCtrlMsg);
        display.setTextSize(1);
        display.setCursor(0, 24);
        display.print(device_hostname);
        display.setCursor(0, 44);
        display.print(sbuf);
        display.display();
    }
    else
    {
        display.clearDisplay();

        display.drawFastHLine(0, 10, 128, SH110X_WHITE);
        display.drawFastHLine(0, 54, 128, SH110X_WHITE);

        // #0 : date and time
        if( true == wifi_connected )
        // if(WiFi.isConnected())
        {
            IPAddress eth_ip_addr = WiFi.localIP();

            ntpPrintLocalTime();

            if( !getLocalTime(&timeinfo))
            {
                LOG_MSGLN("[DISPLAY][NTP][ERROR] Failed to obtain time");

                sprintf(sbuf, "00-00-0000 %c 00:00:00", DISPLAY_HW_UNIT_TYPE[hw_config.hw_unit_type]);

                display.setCursor(0, 0);
                display.setTextSize(1);
                display.setTextColor(SH110X_WHITE);
                display.print(sbuf);
            }
            else
            {
                sprintf(sbuf, "%04d-%02d-%02d %c %02d:%02d:%02d",
                        timeinfo.tm_year + 1900,
                        timeinfo.tm_mon,
                        timeinfo.tm_mday,
                        DISPLAY_HW_UNIT_TYPE[hw_config.hw_unit_type],
                        timeinfo.tm_hour,
                        timeinfo.tm_min,
                        timeinfo.tm_sec
                        );

                display.setCursor(0, 0);
                display.setTextSize(1);
                display.setTextColor(SH110X_WHITE);
                display.print(sbuf);
            }


            // #1: IP ADDR
            display.setCursor(0, LINE_ORIGIN);
            display.setTextSize(1);
            display.setTextColor(SH110X_WHITE);
            sprintf(sbuf, "IP : %3d.%3d.%3d.%3d", eth_ip_addr[0], eth_ip_addr[1], eth_ip_addr[2], eth_ip_addr[3]);
            display.print(sbuf);
        }

        {
            // #2: ACCELEROMETER
            display.setCursor(0, LINE_ORIGIN + LINE_SIZE);
            display.setTextSize(1);
            display.setTextColor(SH110X_WHITE);
            sprintf(sbuf, "XYZ: %1.2f %1.2f %1.2f", acc_x, acc_y, acc_z);
            display.print(sbuf);
        }

        {
            display.setCursor(0, 34);
            display.setTextSize(1);
            display.setTextColor(SH110X_WHITE);
            snprintf(sbuf, 20, bspDisplayLogMsg[!(bspDisplayLogMsgIdx)]);
            display.print(sbuf);
            display.setCursor(0, 44);
            snprintf(sbuf, 20, bspDisplayLogMsg[bspDisplayLogMsgIdx]);
            display.print(sbuf);
        }

        // ctrl message
        {
            snprintf(sbuf, 63, bspDisplayCtrlMsg);
            display.setTextSize(1);
            display.setCursor(0, 56);
            display.print(sbuf);

            if( bspDisplayCtrlTimeout == 1 )
            {
                displayClearCtrlMsg();
            }
            if( bspDisplayCtrlTimeout > 0 )
            {
                bspDisplayCtrlTimeout--;
            }

        }

        display.display();
    }
}

void displayClear()
{
    display.clearDisplay();
    display.display();
}

void displaySplashScreen()
{
    char sbuf[64];
    char sbuild[4] = "";

    switch( SW_VER_BUILD )
    {
        case 0:
            sprintf(sbuild, "rel"); break;
        case 1:
            sprintf(sbuild, "dbg"); break;
        case 2:
            sprintf(sbuild, "rel-qa"); break;
        case 3:
            sprintf(sbuild, "dbg-qa"); break;
        default:
            sprintf(sbuild, "none"); break;
    }


    display.clearDisplay();

    display.setCursor(10, 10);
    display.setTextSize(2);
    display.setTextColor(SH110X_WHITE);
    display.print("[Auralys]");

    display.setCursor(30, 30);
    display.setTextSize(1);
    display.print("by UniMore");

    display.setCursor(2, 44);
    display.setTextSize(1);
    display.setTextColor(SH110X_WHITE);
    sprintf(sbuf, "2025 - ver.%1d.%1d.%1d.%s", SW_VER_MJR, SW_VER_MIN, SW_VER_REV, sbuild);
    display.print(sbuf);

    display.display();
}

void displayCtrlMsg(char* msg)
{
    if( NULL != msg )
    {

        snprintf(bspDisplayCtrlMsg, 63, msg);
    }
}

void displayCtrlLogMsg(char* msg)
{
    char sbuf[64];

    if( NULL != msg )
    {
        bspDisplayLogMsgIdx = !(bspDisplayLogMsgIdx);
        snprintf(&bspDisplayLogMsg[bspDisplayLogMsgIdx][0], 20, msg);

    }
}

void displayCtrlMsgTemp(char* msg, uint8_t timeout)
{
    char sbuf[64];

    if( NULL != msg )
    {
        bspDisplayCtrlTimeout = timeout;
        snprintf(bspDisplayCtrlMsg, 63, msg);

    }
}

// void displayClearCtrlMsg(uint8_t x, uint8_t y, uint8_t cur_size, char* msg)
void displayClearCtrlMsg()
{
    snprintf(bspDisplayCtrlMsg, 63, "                                                  ");
}

void displayCtrlON()
{

}

void displayCtrlOFF()
{

}
