/* ============================================================================= */
/* NTP Network Time Protocol                                                     */
/* ============================================================================= */
#define NTP_RETRY_MAX (32)


void ntpPrintLocalTime()
{
    struct tm timeinfo;
    if( !getLocalTime(&timeinfo))
    {
        LOG_MSGLN("[NTP][WiFi][ERROR] Failed to obtain time");
        return;
    }

// #ifdef DEBUG
// Serial.println(&timeinfo, "%A, %B %d %Y %H:%M:%S");
// #endif
}

bool ntpTimeSyncWiFi()
{
    const char* ntpServer = "pool.ntp.org";

    bool ret = false;

    bspSetCpuFrequencyMhz(BSP_CPU_MHZ_MAX);

    if( false == wifi_connected )
    {
        ret = bspEnableWiFi();
    }

    delay(100);

    if( true == wifi_connected )
    {
        LOG_MSGLN("[NTP][WiFi] NTP request to pool.ntp.org");
        // init and get the time
        configTime(1 /*gmtOffset_sec*/, 0 /*daylightOffset_sec*/, ntpServer);
        ntpPrintLocalTime();
    }

    // if( true == ret )
    // {
    // bspDisableWiFi();
    // }

    bspSetCpuFrequencyMhz(bspCpuMhzPrevious);


    /* CHECK for TIME SYNC */
    if( 1970 == esp32_rtc.getYear())
    {
        LOG_MSGLN("[NTP][WiFi][ERROR] Failed to sync time over WiFi.");
        return false;
    }

    return true;
}

void ntpSetup()
{
    ntpTimeSyncWiFi();
}

void ntpLoop()
{
    /* nothing to do */
}