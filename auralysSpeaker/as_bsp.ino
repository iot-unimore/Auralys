/* ============================================================================= */
/* BSP & PLATFORM MANAGEMENT                                                     */
/* ============================================================================= */

void bspReboot()
{
    delay(200);

    ESP.restart();

    /* set GPIO0=LOW to allow fw update on restart */
    // TODO: use a GPIO connected to RST to pull down and hw-reset instead of ESP.restart()
    // pinMode(0, OUTPUT);
    // digitalWrite(0, LOW);
    // delay(200);
}

void bspReset()
{
    uint8_t tmp8;
    WiFiManager wm;

    /* wifiManager erase credentials */
    wm.resetSettings();

    /* deactivate device */
    bspActivated = 0;
    eepromReadBytes(&tmp8, EE_SYS_INIT_FLAG_OFFS, EE_SYS_INIT_FLAG_SIZE);
    tmp8 &= ~(EE_SYS_INIT_BSPACTIVATED_MSK);
    eepromWriteBytes(EE_SYS_INIT_FLAG_OFFS, &tmp8, EE_SYS_INIT_FLAG_SIZE);
    EEPROM.commit();
}

void bspPrintMac(const unsigned char* mac)
{
    LOG_PRINTF("%02X:%02X:%02X:%02X:%02X:%02X\n", mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
}

void bspMacTest()
{
    unsigned char mac_base[6] = { 0 };
    esp_efuse_mac_get_default(mac_base);
    esp_read_mac(mac_base, ESP_MAC_WIFI_STA);
    unsigned char mac_local_base[6] = { 0 };
    unsigned char mac_uni_base[6] = { 0 };
    esp_derive_local_mac(mac_local_base, mac_uni_base);
    LOG_MSG("Local Address: ");
    bspPrintMac(mac_local_base);
    LOG_MSG("\nUni Address: ");
    bspPrintMac(mac_uni_base);
    LOG_MSG("MAC Address: ");
    bspPrintMac(mac_base);
}

void bspDisableWiFi()
{
    WiFi.disconnect(true);
    WiFi.mode(WIFI_OFF);
    wifi_connected = false;
}

bool bspEnableWiFi()
{
    bool rv = false;
    WiFiManager wm;

    bspSetCpuFrequencyMhz(BSP_CPU_MHZ_MAX);

    LOG_MSG("[HTTP] device hostname:");
    LOG_MSGLN(device_hostname);


    WiFi.setHostname(device_hostname);
    WiFi.mode(WIFI_STA);
    WiFi.disconnect(false);

    wm.setTitle("Auralys");
    wm.setConfigPortalTimeout(1); // auto close configportal after n seconds
    wm.setAPClientCheck(true); // avoid timeout if client connected to softap
    wm.setMinimumSignalQuality(20); // set min RSSI (percentage) to show in scans, null = 8%

    rv = wm.autoConnect(device_hostname);

    if( rv )
    {
        LOG_MSGLN("[BSP] bspEnableWiFi .. OK")
        LOG_MSG("[BSP] Local ESP32 IP: ");
        LOG_MSGLN(WiFi.localIP());

        wifi_connected = true;

        rv = true;
    }
    else
    {
        LOG_MSGLN("[BSP][ERROR] bspEnableWiFi .. FAILED!")

        wifi_connected = false;

        rv = false;
    }

    bspSetCpuFrequencyMhz(bspCpuMhzPrevious);

    return rv;
}

uint32_t bspScanWiFi()
{
    LOG_MSGLN("\n[BSP] WiFi Scanning ... ");

    uint32_t n = WiFi.scanNetworks();

    if( n == 0 )
    {
        LOG_MSGLN("no networks found");
    }
    else
    {
        LOG_MSG(n);
        LOG_MSGLN("[BSP] WiFi networks found:");
        for( int i = 0; i < n; ++i )
        {
            // Print SSID and RSSI for each network found
            LOG_MSG(i + 1);
            LOG_MSG(": ");
            LOG_MSG(WiFi.SSID(i));
            LOG_MSG(" (");
            LOG_MSG(WiFi.RSSI(i));
            LOG_MSG(")");
            LOG_MSGLN((WiFi.encryptionType(i) == WIFI_AUTH_OPEN) ? " " : "*");
            delay(10);
        }
        LOG_MSGLN();
    }
    return n;

}

void bspSetCpuFrequencyMhz(int freq_mhz)
{
    /*
       Frequency	Power consumption
       240Mhz	    66.8mA
       160Mhz	    45.9mA
       80Mhz	    33.2mA
       40Mhz	    19.88mA
       20Mhz	    15.43mA
       10Mhz	    13.19mA
     */

    bspCpuMhzPrevious = bspCpuMhzCurrent;

    switch( freq_mhz )
    {
        case (240):
            setCpuFrequencyMhz(240);
            bspCpuMhzCurrent = 240;
            break;
        case (160):
            setCpuFrequencyMhz(160);
            bspCpuMhzCurrent = 160;
            break;
        case (80):
            setCpuFrequencyMhz(80);
            bspCpuMhzCurrent = 80;
            break;
        case (40):
            setCpuFrequencyMhz(40);
            bspCpuMhzCurrent = 40;
            break;
        case (20):
            setCpuFrequencyMhz(20);
            bspCpuMhzCurrent = 20;
            break;
        case (10):
            setCpuFrequencyMhz(10);
            bspCpuMhzCurrent = 10;
            break;
        default:
            setCpuFrequencyMhz(10);
            bspCpuMhzCurrent = 10;
            break;
    }
}

void bspI2CScan()
{
    byte error, address;
    int nDevices;

    Serial.println("Scanning...");

    nDevices = 0;
    for( address = 1; address < 127; address++ )
    {

        // The i2c_scanner uses the return value of
        // the Write.endTransmisstion to see if
        // a device did acknowledge to the address.
        Wire.beginTransmission(address);
        error = Wire.endTransmission();

        if( error == 0 )
        {
            Serial.print("I2C device found at address 0x");
            if( address < 16 )
            {
                Serial.print("0");
            }
            Serial.print(address, HEX);
            Serial.println("  !");

            nDevices++;
        }
        else if( error == 4 )
        {
            Serial.print("Unknown error at address 0x");
            if( address < 16 )
            {
                Serial.print("0");
            }
            Serial.println(address, HEX);
        }
    }
    if( nDevices == 0 )
    {
        Serial.println("No I2C devices found\n");
    }
    else
    {
        Serial.println("done\n");
    }
}

void bspWiFiConfig(uint32_t cfgTimeout)
{
    bool rv = false;
    WiFiManager wm;

    LOG_MSGLN("[BSP] entering config webportal");

    bspSetCpuFrequencyMhz(BSP_CPU_MHZ_MAX);

    WiFi.setHostname(device_hostname);
    WiFi.mode(WIFI_STA);
    WiFi.disconnect(false);

    /*
     * erase wifi credentials and prepare WiFiManager settings
     */
    wm.resetSettings();

    const char* wm_menu[] = { "wifi", "exit" };
    wm.setShowInfoUpdate(false);
    wm.setShowInfoErase(false);
    wm.setMenu(wm_menu, 2);


    wm.setTitle("Auralys, Hello!");

    // force to be Google DNS as a workaround for Android phones
    wm.setAPStaticIPConfig(IPAddress(8, 8, 8, 8), IPAddress(8, 8, 8, 8), IPAddress(255, 255, 255, 0));

    // wm.setClass("invert");
    // wm.setConnectTimeout(20); // how long to try to connect for before continuing

    if( cfgTimeout > 0 )
    {
        wm.setConfigPortalTimeout(cfgTimeout); // auto close configportal after n seconds
    }

    wm.setCaptivePortalEnable(true); // if false, disable captive portal redirection
    wm.setAPClientCheck(false); // if false, timeout captive portal even if a STA client connected to softAP (false)
    // wifi scan settings
    // wm.setRemoveDuplicateAPs(false);     // do not remove duplicate ap names (true)
    wm.setMinimumSignalQuality(15); // set min RSSI (percentage) to show in scans, null = 8%
    // wm.setShowInfoErase(false);          // do not show erase button on info page
    // wm.setScanDispPerc(true);            // show RSSI as percentage not graph icons
    wm.setBreakAfterConfig(true); // always exit configportal even if wifi save fails
    wm.setSaveConnect(true); // lets you disable automatically connecting after save from webportal

    rv = wm.autoConnect(device_hostname);

    if( rv )
    {
        LOG_MSGLN("[BSP] wifiConfig .. OK");

    }
    else
    {
        LOG_MSGLN("[BSP] wifiConfig failure");
    }



    /* set bsp_activation_flag */
    if( rv )
    {
        uint8_t tmp8;

        LOG_MSGLN("[BSP] device activated. ");
        bspActivated = 1;
        eepromReadBytes(&tmp8, EE_SYS_INIT_FLAG_OFFS, EE_SYS_INIT_FLAG_SIZE);
        tmp8 |= (EE_SYS_INIT_BSPACTIVATED_MSK);
        eepromWriteBytes(EE_SYS_INIT_FLAG_OFFS, &tmp8, EE_SYS_INIT_FLAG_SIZE);
        EEPROM.commit();
    }

    bspSetCpuFrequencyMhz(bspCpuMhzPrevious);

    delay(300);
    bspReboot();
}

void bspSetup()
{
    // bspConfig = BSP_CONFIG_DEFAULT;
    // bspChipID = ESP.getChipModel();

    /* hostname from hw */
    char sbuf[16];
    sprintf(sbuf, "%012llx\r\n", ESP.getEfuseMac());
    for( int i = 0; i < 9; i++ )
    {
        // device_hostname[15 - i] = hw_config.hw_pcb_uuid4[31 - i];
        device_hostname[15 - i] = sbuf[12 - i];
    }

    if( bspActivated == true )
    {
        ledRgbSetColor(ledRgbColorWhite);

        int i = 0;
        while((i < BSP_RETRY_MAX) && (false == wifi_connected))
        {
            i++;
            displayCtrlMsg((char*) "WiFi Connect..");
            displayLoop();
            bspEnableWiFi();
            if( false == wifi_connected )
            {
                displayCtrlMsg((char*) "WiFi failed..");
                displayLoop();
                bspDisableWiFi();
                delay(2000);
            }
        }

        /* fallback on config */
        if( false == wifi_connected )
        {
            ledRgbSetColor(ledRgbColorBlue);
            bspDisplayCtrlFullscreen = true;
            displayCtrlMsg((char*) "Config Mode..");
            displayLoop();
            bspWiFiConfig(0);
            bspDisplayCtrlFullscreen = false;
        }
    }
    else
    {
        ledRgbSetColor(ledRgbColorBlue);
        bspDisplayCtrlFullscreen = true;
        displayCtrlMsg((char*) "Config Mode..");
        displayLoop();
        bspWiFiConfig(0);
        bspDisplayCtrlFullscreen = false;
    }

    /* no need to sleep on WiFi */
    if( WiFi.isConnected() && (WiFi.status() == WL_CONNECTED))
    {
        WiFi.setSleep(false);
        esp_wifi_set_ps(WIFI_PS_NONE);        
    }

    ledRgbSetColor(ledRgbColorOff);

    /* DEFAULT: Start at 10Mhz for low power consumption */
    // bspSetCpuFrequencyMhz(BSP_CPU_MHZ_DEFAULT);
}

void bspLoop()
{
    if((!(WiFi.isConnected())) || (WiFi.status() != WL_CONNECTED))
    {
        LOG_MSGLN("Wifi Connection Lost");
        displayCtrlMsg((char*) "WiFi Connect Lost");
        displayLoop();

        wifi_connected = false;

        ledRgbSetColor(ledRgbColorWhite);

        int i = 0;
        while((i < BSP_RETRY_MAX) && (false == wifi_connected))
        {
            i++;
            displayCtrlMsg((char*) "WiFi Connect..");
            displayLoop();

            bspEnableWiFi();
            if( false == wifi_connected )
            {
                displayCtrlMsg((char*) "WiFi failed..");
                displayLoop();
                bspDisableWiFi();
                delay(2000);
            }
        }

        /* fallback on config */
        if( false == wifi_connected )
        {
            ledRgbSetColor(ledRgbColorBlue);
            bspDisplayCtrlFullscreen = true;
            displayCtrlMsg((char*) "Config Mode..");
            displayLoop();
            bspWiFiConfig(120); // 2min timeout
            bspDisplayCtrlFullscreen = false;
        }

        WiFi.setSleep(false);
        esp_wifi_set_ps(WIFI_PS_NONE);        

        ledRgbSetColor(ledRgbColorOff);
    }
}