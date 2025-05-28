/* ============================================================================= */
/* HTTPUPDATE WiFi && NBIOT                                                      */
/* ============================================================================= */


void printPercent(uint32_t readLength, uint32_t contentLength)
{
#ifdef DEBUG
    // If we know the total length
    if((contentLength != -1) && (contentLength > 0))
    {
        LOG_MSG("\r ");
        LOG_MSG((100.0 * readLength) / contentLength);
        LOG_MSGLN('%');
    }
    else
    {
        LOG_MSGLN(readLength);
    }
#endif
}

void updateFromFS()
{
    File updateBin = FFat.open("/update.bin");
    if( updateBin )
    {
        if( updateBin.isDirectory())
        {
            LOG_MSGLN("Error, file is a directory");
            updateBin.close();
            return;
        }

        size_t updateSize = updateBin.size();

        if( updateSize > 0 )
        {
            LOG_MSGLN("Begin update");
            performUpdate(updateBin, updateSize);
        }
        else
        {
            LOG_MSGLN("Error, empty file");
        }

        updateBin.close();

        // whe finished remove the binary from sd card to indicate end of the process
        // fs.remove("/update.bin");
    }
    else
    {
        LOG_MSGLN("Error, cannot open update file");
    }
}

void performUpdate(Stream &updateSource, size_t updateSize)
{
    if( Update.begin(updateSize))
    {
        size_t written = Update.writeStream(updateSource);
        if( written == updateSize )
        {
            LOG_MSGLN("Written: " + String(written) + " successfully");
        }
        else
        {
            LOG_MSGLN("Partial write: " + String(written) + "/" + String(updateSize));
            /* ToDo: call system reset here ?*/
        }

        if( Update.end())
        {
            LOG_MSGLN("OTA successful");
            if( Update.isFinished())
            {
                LOG_MSGLN("OTA done, reset");
                delay(3000);
                ESP.restart();
            }
            else
            {
                LOG_MSGLN("Error during OTA");
                /* ToDo: call system reset here ?*/
            }
        }
        else
        {
            LOG_MSGLN("OTA Error: " + String(Update.getError()));
            /* ToDo: call system reset here ?*/

        }
    }
    else
    {
        LOG_MSGLN("OTA Error: no space left on the device");
        /* ToDo: call system reset here ?*/

    }
}

/*
 *  WiFi tools
 */
void http_update_started()
{
    LOG_MSGLN("CALLBACK:  HTTP update process started");
    ledRgbSetColor(ledRgbColorViolet);
}

void http_update_finished()
{
    LOG_MSGLN("CALLBACK:  HTTP update process finished");
    ledRgbSetColor(ledRgbColorOff);
}

void http_update_progress(int cur, int total)
{
    LOG_PRINTF("CALLBACK:  HTTP update process at %d of %d bytes...\n", cur, total);

    if( ledRgbColorViolet == ledRgbGetColor())
    {
        ledRgbSetColor(ledRgbColorOff);
    }
    else
    {
        ledRgbSetColor(ledRgbColorViolet);

    }
}

void http_update_error(int err)
{
    ledRgbSetColor(ledRgbColorRed);
    delay(1000);
    LOG_PRINTF("CALLBACK:  HTTP update fatal error code %d\n", err);
    ledRgbSetColor(ledRgbColorOff);
}

/*
 * MAIN
 */

void httpUpdateInit()
{

/* nothing to do here */
}

/*
 * WiFi update
 */
int8_t httpWiFiUpdate()
{
    int8_t rv = -1;

    WiFiClient gsmClient;
    t_httpUpdate_return ret = HTTP_UPDATE_FAILED;

    bspSetCpuFrequencyMhz(BSP_CPU_MHZ_MAX);

    // if((WiFiMulti.run(wifiConnectTimeoutMs) == WL_CONNECTED))
    if( true == wifi_connected )
    {

        LOG_MSGLN("[HTTP-UPDATE][WiFi] beginning procedure..");
        ledRgbSetColor(ledRgbColorViolet);
        LOG_MSGLN(WiFi.localIP());

        /* software version and hw platform */
        String SwVer;
        SwVer = "";
        SwVer.concat(BRWS_SW_CODENAME); SwVer.concat("_");
        SwVer.concat(BRWS_SW_PLATFORM); SwVer.concat("_");
        SwVer.concat(BRWS_HW_CFG_CPU_ARCH); SwVer.concat("_");
        SwVer.concat(BRWS_HW_CFG_CPU_TYPE); SwVer.concat("_");
        SwVer.concat(SW_VER_MJR); SwVer.concat(".");
        SwVer.concat(SW_VER_MIN); SwVer.concat(".");
        SwVer.concat(SW_VER_REV); SwVer.concat("_");
        SwVer.concat(SW_VER_BUILD);

        /* http update callbacks */
        httpUpdate.onStart(http_update_started);
        httpUpdate.onEnd(http_update_finished);
        httpUpdate.onProgress(http_update_progress);
        httpUpdate.onError(http_update_error);


        if( HTTP_UPDATE_OK != ret )
        {

#ifdef DEBUG
            LOG_MSGLN("[HTTP-UPDATE][WiFi] R&D-SERVER : connecting...");
            ret = httpUpdate.update(gsmClient, HTTPUPDATE_RD_SERVER, 80, "/brws_iot/update/", SwVer);
#else
            LOG_MSGLN("[HTTP-UPDATE][WiFi] PRODUCTION-SERVER : connecting....");

            // ToDo: IMPORTANT: uncomment this one once we switch production server to brainworks.it !!
            // t_httpUpdate_return ret = httpUpdate.update(gsmClient, HTTPUPDATE_PRODUCTION_SERVER, 80, "/iot/update/", SwVer);

            t_httpUpdate_return ret = httpUpdate.update(gsmClient, HTTPUPDATE_PRODUCTION_SERVER, 80, "/brws_iot/update/", SwVer);
#endif

            switch( ret )
            {
                case HTTP_UPDATE_FAILED:
                    LOG_PRINTF("[HTTP-UPDATE][WiFi] HTTP_UPDATE_FAILED Error (%d): %s\n", httpUpdate.getLastError(), httpUpdate.getLastErrorString().c_str());
                    rv = -1;
                    break;

                case HTTP_UPDATE_NO_UPDATES:
                    LOG_MSGLN("[HTTP-UPDATE][WiFi] HTTP_UPDATE_NO_UPDATES");
                    rv = 0;
                    break;

                case HTTP_UPDATE_OK:
                    LOG_MSGLN("[HTTP-UPDATE][WiFi] HTTP_UPDATE_OK");
                    rv = 0;
                    break;
            }
        }
        else
        {
            rv = 0;
        }

        LOG_MSGLN("[HTTP-UPDATE][WiFi] ...connecting DONE.");
        ledRgbSetColor(ledRgbColorOff);
    }

    bspSetCpuFrequencyMhz(bspCpuMhzPrevious);

    return rv;
}

void httpUpdateLoop()
{
    int8_t ret = -1;

    bspSetCpuFrequencyMhz(BSP_CPU_MHZ_MAX);

    /* 1ST: WiFi update (faster) */
    if( wifi_enabled )
    {
        if( 0 != ret )
        {
            // bspEnableWiFi();

            ret = httpWiFiUpdate();

            // bspDisableWiFi();

            if( 0 == ret )
            {
                httpUpdate_flag = true;
            }
        }
    }

    bspSetCpuFrequencyMhz(bspCpuMhzPrevious);
}
