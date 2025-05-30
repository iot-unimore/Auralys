/* ============================================================================= */
/* DISPLAY CONTROL */
/* ============================================================================= */
#define LINE_ORIGIN (14)
#define LINE_SIZE (10)

void displaySetup()
{
    display.begin(SCREEN_I2C_ADDR, true);
    // display.setContrast (0); // dim display

    display.clearDisplay();
    display.display();
}

void displayLoop()
{
    char sbuf[64];
    struct tm timeinfo;

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
        }
        else
        {
            sprintf(sbuf, "%04d-%02d-%02d   %02d:%02d:%02d",
                    timeinfo.tm_year + 1900,
                    timeinfo.tm_mon,
                    timeinfo.tm_mday,
                    timeinfo.tm_hour,
                    timeinfo.tm_min,
                    timeinfo.tm_sec
                    );

            display.setCursor(0, 0);
            display.setTextSize(1);
            display.setTextColor(SH110X_WHITE);
            // display.setTextColor(SH110X_BLACK, SH110X_WHITE); // 'inverted' text
            display.print(sbuf);

            // Serial.println(&timeinfo, "%A, %B %d %Y %H:%M:%S");
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

    uint8_t l = 0;
    for(int i = 34; i < 45; i += 10)
    {
        display.setCursor(0, i);
        display.setTextSize(1);
        display.setTextColor(SH110X_WHITE);
        sprintf(sbuf, "%01d: ", l++);
        display.print(sbuf);
    }

    // ctrl message
    {
        snprintf(sbuf, 63, bspDisplayCtrlMsg);
        display.setTextSize(1);
        display.setCursor(0, 56);
        display.print(sbuf);

        if( bspDisplayTimeout == 1 )
        {
            displayClearCtrlMsg();
        }
        if( bspDisplayTimeout > 0 )
        {
            bspDisplayTimeout--;
        }

    }

    display.display();
}

void displayClear()
{
    display.clearDisplay();
    display.display();
}

void displaySplashScreen()
{
    char sbuf[64];

    display.clearDisplay();

    display.setCursor(10, 10);
    display.setTextSize(2);
    display.setTextColor(SH110X_WHITE);
    display.print("[Auralys]");

    display.setCursor(30, 30);
    display.setTextSize(1);
    display.print("by UniMore");

    display.setCursor(4, 40);
    display.setTextSize(1);
    display.setTextColor(SH110X_WHITE);
    sprintf(sbuf, " 2025 - version %1d.%1d", SW_VER_MJR, SW_VER_MIN);
    display.print(sbuf);

    // display.setTextColor(SH110X_BLACK, SH110X_WHITE); // 'inverted' text
    // display.println(3.141592);

    // display.setTextSize(2);
    // display.setTextColor(SH110X_WHITE);
    // display.print("0x"); display.println(0xDEADBEEF, HEX);

    display.display();
}

// void displayCtrlMsg(uint8_t x, uint8_t y, uint8_t cur_size, char* msg)
void displayCtrlMsg(char* msg)
{
    char sbuf[64];

    if( NULL != msg )
    {

        snprintf(bspDisplayCtrlMsg, 63, msg);

    }
}

void displayCtrlMsgTemp(char* msg, uint8_t timeout)
{
    char sbuf[64];

    if( NULL != msg )
    {
        bspDisplayTimeout = timeout;
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

#if 0
void displayCtrlLoop()
{
    // char sbuf[32];
    // time_t t = ntpClient.getUnixTime();

    // sprintf(sbuf, "%4d-%02d-%02d %2d:%02d:%02d",
    // year(t),
    // month(t),
    // day(t),
    // hour(t),
    // minute(t),
    // second(t));

    // u8g2.clearBuffer();
    // u8g2.setFont(u8g2_font_6x10_tf);
    // u8g2.setFontMode(0);
    // u8g2.drawStr(0, 8, sbuf);

    // sprintf(sbuf, "T(C) %2.1f/%2.1f", tempExternal, tempInternal);
    // u8g2.setFontMode(0);
    // u8g2.drawStr(0, 24, sbuf);
    // u8g2.sendBuffer();




/* compute delta time from last check and handle wraparound */
    unsigned long deltaTimeMs = millis();
    deltaTimeMs = (displayCTRLTime <= deltaTimeMs) ?
                  (deltaTimeMs - displayCTRLTime) : (0xFFFFFFFF - (displayCTRLTime - deltaTimeMs));

    unsigned long deltaPowerOffTimeMs = millis();
    deltaPowerOffTimeMs = (displayPowerOffTime <= deltaPowerOffTimeMs) ?
                          (deltaPowerOffTimeMs - displayPowerOffTime) : (0xFFFFFFFF - (displayPowerOffTime - deltaPowerOffTimeMs));

/* POwerOFF with 3X periodic power on */
    if((DISPLAY_REFRESH_MS < deltaTimeMs) &&
       (deltaPowerOffTimeMs > DISPLAY_POWEROFF_MS))
    {
        if( deltaPowerOffTimeMs > DISPLAY_WAKEUP_MS )
        {
            displayCtrlON();
        }
        else
        {
            displayCtrlOFF();
            displayCTRLTime = millis();
            return;
        }
    }

/* normal update */
    if((eeprom_dirty_f == true) && (buttonRSTTime == buttonRSTTimeZero) && (buttonRST_f == false))
    {
        char sbuf[21];

        if( DISPLAY_REFRESH_MS < deltaTimeMs )
        {
// oled1.clear();
            oled1.setTextSize(2);
            oled1.setCursor(0); oled1.write("TO CONFIG");

// sprintf(sbuf,"DHCP:%s Ee:%s",
// (eth_ip_dhcp_f==true)?"on":"off", (eeprom_dirty_f==true)?"*":"-" );
// oled1.setTextSize(1);
// oled1.setCursor(1); oled1.write(sbuf);

/* Display Line #2-5 : IP config */
            oled1.setTextSize(1);

            sprintf(sbuf, "MAC: %02x:%02x:%02x:%02x:%02x:%02x",
                    eth_ip_mac[0], eth_ip_mac[1], eth_ip_mac[2], eth_ip_mac[3], eth_ip_mac[4], eth_ip_mac[5]);
            oled1.setCursor(3); oled1.write(sbuf);
            sprintf(sbuf, "IP : %3d.%3d.%3d.%3d", eth_ip_addr[0], eth_ip_addr[1], eth_ip_addr[2], eth_ip_addr[3]);
            oled1.setCursor(4); oled1.write(sbuf);
            sprintf(sbuf, "MSK: %3d.%3d.%3d.%3d", eth_ip_msk[0], eth_ip_msk[1], eth_ip_msk[2], eth_ip_msk[3]);
            oled1.setCursor(5); oled1.write(sbuf);
            sprintf(sbuf, "GW : %3d.%3d.%3d.%3d", eth_ip_gw[0], eth_ip_gw[1], eth_ip_gw[2], eth_ip_gw[3]);
            oled1.setCursor(6); oled1.write(sbuf);
            sprintf(sbuf, "DNS: %3d.%3d.%3d.%3d", eth_ip_dns[0], eth_ip_dns[1], eth_ip_dns[2], eth_ip_dns[3]);
            oled1.setCursor(7); oled1.write(sbuf);

/* update timeslot */
            displayCTRLTime = millis();
        }
    }

/* skip if we are in reset mode or need_config mode*/
    if((buttonRSTTime != buttonRSTTimeZero) || (buttonRST_f != false) || (eeprom_dirty_f == true))
    {
        return;
    }

    if( DISPLAY_REFRESH_MS < deltaTimeMs )
    {
        char sbuf[21];
        char fbuf[5];
        char fbuf2[5];
// time_t dateTime = now();

/* check for page change */
        if( displayPagePrv != displayPageCur )
        {
            oled1.clear();
            displayPagePrv = displayPageCur;
        }

/*
 * PAGE #0 : SYSTEM INFO
 */
        if( displayPageCur == 0 )
        {
            time_t local = euCentral.toLocal(now(), &timeChangeRule);
/* Display Line #0: clock value */
            sprintf(sbuf, "%04d-%02d-%02d %02d:%02d:%02d",
                    year(local), month(local), day(local), hour(local), minute(local), second(local));

            oled1.setTextSize(1);
            oled1.setCursor(0, 0); oled1.write(sbuf);

/* Display Line #1: show battery/main values */
            dtostrf(inV12V, 4, 1, fbuf);
            dtostrf(inVbat, 3, 1, fbuf2);
            sprintf(sbuf, "V:%s %s DHCP:%s Ee:%s",
                    fbuf, fbuf2, (eth_ip_dhcp_f == true) ? "on" : "off", (eeprom_dirty_f == true) ? "*" : "-");
            oled1.setTextSize(1);
            oled1.setCursor(1); oled1.write(sbuf);

/* Display Line #2-5 : IP config */
            oled1.setTextSize(1);

            sprintf(sbuf, "MAC: %02x:%02x:%02x:%02x:%02x:%02x",
                    eth_ip_mac[0], eth_ip_mac[1], eth_ip_mac[2], eth_ip_mac[3], eth_ip_mac[4], eth_ip_mac[5]);
            oled1.setCursor(3); oled1.write(sbuf);
            sprintf(sbuf, "IP : %3d.%3d.%3d.%3d", eth_ip_addr[0], eth_ip_addr[1], eth_ip_addr[2], eth_ip_addr[3]);
            oled1.setCursor(4); oled1.write(sbuf);
            sprintf(sbuf, "MSK: %3d.%3d.%3d.%3d", eth_ip_msk[0], eth_ip_msk[1], eth_ip_msk[2], eth_ip_msk[3]);
            oled1.setCursor(5); oled1.write(sbuf);
            sprintf(sbuf, "GW : %3d.%3d.%3d.%3d", eth_ip_gw[0], eth_ip_gw[1], eth_ip_gw[2], eth_ip_gw[3]);
            oled1.setCursor(6); oled1.write(sbuf);
            sprintf(sbuf, "DNS: %3d.%3d.%3d.%3d", eth_ip_dns[0], eth_ip_dns[1], eth_ip_dns[2], eth_ip_dns[3]);
            oled1.setCursor(7); oled1.write(sbuf);

        } // END PAGE #0

/*
 * PAGE #1 : COUNTERS
 */
        if( displayPageCur >= 1 )
        {
/* Display Line #0: clock value */
// sprintf(sbuf,"%04d-%02d-%02d %02d:%02d:%02d",
// year(),month(),day(),hour(),minute(),second() );
// oled1.setTextSize(1);
// oled1.setCursor(0,0); oled1.write(sbuf);

/* Display Line #3,#4,#5,#6 : counters */
            int8_t i;
            for(i = (4 * (displayPageCur - 1)); ((i < (4 * (displayPageCur))) && (i < COUNTER_NUM)); i++)
            {
                sprintf(sbuf, "C%d:%8d", i, (int) counter64[i]);
                oled1.setTextSize(2);
                oled1.setCursor(0 + i * 2); oled1.write(sbuf);
            }

        } // END PAGE #1


/* update timeslot */
        displayCTRLTime = millis();
    }

}

#endif