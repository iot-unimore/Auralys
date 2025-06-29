/*
 *    _  _   _ ___    _   _ __   _____
 *   /_\| | | | _ \  /_\ | |\ \ / / __|
 *  / _ \ |_| |   / / _ \| |_\ V /\__ \
 * /_/ \_\___/|_|_\/_/ \_\____|_| |___/
 *
 *=BEGIN AURALIS LICENSE
 *
 * This file is part of the IOT-UNIMORE "Auralis" project.
 *
 * Copyright (c) 2025 Gianluca Filippini. All rights reserved.
 *
 * Licensed under the MIT License (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 * https://mit-license.org/
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 *
 *=END AURALYS LICENSE
 *
 */

/* ============================================================================= */
/* internal libraries                                                            */
/* ============================================================================= */
#include <Arduino.h>

#include <WiFi.h>
#include <WiFiManager.h>
#include <esp_wifi.h>
#include <HTTPClient.h>
#include <HTTPUpdate.h>
#include <esp_adc/adc_cali.h> // esp_adc_cal.h>
#include <esp32-hal-adc.h>

#include <ArduinoJson.h>

#include "stdint.h"
#include "esp_adc/adc_continuous.h"
#include "esp_task_wdt.h"
#include "esp32/ulp.h"
#include "soc/rtc_cntl_reg.h"
#include "driver/rtc_io.h"
#include "esp_mac.h"

#include <TimeLib.h>
#include <Time.h>
#include <EEPROM.h>
// #include "Timezone.h"

#include <Update.h>
#include <CRC32.h>
#include <esp_partition.h>
#include <esp_ota_ops.h>
#include "FS.h"
// #include "SPIFFS.h"
#include "FFat.h"


/* ============================================================================= */
/* SOFTWARE REVISION GLOBALS&DEFINES SECTION                                     */
/* ============================================================================= */
#define BRWS_SW_PLATFORM_SIZE_MAX (16)
#define BRWS_SW_PLATFORM  "brws"
#define BRWS_SW_CODENAME_SIZE_MAX (8)
#define BRWS_SW_CODENAME  "auralysS"

/* temporary since there is no ST25 eeprom */
#define BRWS_HW_CFG_CPU_ARCH "lolin"
#define BRWS_HW_CFG_CPU_TYPE "S3mini"

/* Software Revision - BEGIN */
#define SW_VER_MJR    (0) /* NOTE: 0->255, 1byte coded */
#define SW_VER_MIN    (3) /* NOTE: 0->15,   4bit coded */
#define SW_VER_REV    (2) /* NOTE: 0->3,    2bit coded  */

/* switch define for debug/release + qa build type */
#define DEBUG
// #define QA

/* SW VERSIONS for OTA : 0->3, 2 bit coded
 * DO NOT CHANGE THE FOLLOWING DEFINES FOR SW_VER_BUILD
 * this is a pre-defined value which is coded as follow:
 *  0 : release
 *  1 : debug
 *  2 : release-qa
 *  3 : debug-qa
 */
#ifdef DEBUG
#define LOG_MSG(...)        { Serial.print(__VA_ARGS__); }
#define LOG_MSGLN(...)      { Serial.println(__VA_ARGS__); }
#define LOG_PRINTF(...)     { Serial.printf(__VA_ARGS__); }
#define LOG_PRINTFLN(...)   { Serial.printf(__VA_ARGS__); Serial.printf("\n"); }

#ifdef QA
#define SW_VER_BUILD  (3)
#else
#define SW_VER_BUILD  (1)
#endif
#else
#define LOG_MSG(...)        /* blank */
#define LOG_MSGLN(...)      /* blank */
#define LOG_PRINTF(...)     /* blank */
#define LOG_PRINTFLN(...)   /* blank */
#ifdef QA
#define SW_VER_BUILD  (2)
#else
#define SW_VER_BUILD  (0)
#endif
#endif
/* Software Revision - END */

/* timing macros */
#define ONESEC_USECS           (1000000L)
#define ONESEC_MSECS              (1000L)
#define ONEMS_USECS               (1000L)
#define ONEHOUR_SECS              (3600L)
#define ONEMIN_SECS                 (60L)
#define ONEMS_MSECS                   (1)


/* ============================================================================= */
/* HARDWARE REVISION GLOBALS&DEFINES SECTION                                     */
/* ============================================================================= */
#include "auralys_hwconfig.h"

#define UART_MKS_TX_PIN (43)
#define UART_MKS_RX_PIN (44)
#define UART_MKS_BAUD (38400)

#define I2S_SDA_PIN (35)
#define I2S_SCL_PIN (36)

/* hostname from hw */
char device_hostname[16 + 1] = "auspkr-000000000";

/* default/empty hw configuration (read from nfctag at boot) */
HW_PCB_CONFIG_T hw_config = {
    0, /* hw_section_size */
    1, /* hw_descriptor_mjr */
    0, /* hw_descriptor_min */
    "unknown", /* hw_codename */
    "unknown", /* hw_cpu_arch */
    "unknown", /* hw_cpu_type */
    0, /* hw_pcb_ver_mjr */
    0, /* hw_pcb_ver_min */
    "01234567890123456789012345678901", /* hw_pcb_uuid4 */
    0, /* hw_unit_type */
    0, /* hw_unit_orientation */
    1, /* hw_mks_slave_addr */
    10, /* hw_mks_speed */
    1 /* hw_mks_accel */
};

/* ============================================================================= */
/* SOFTWARE LOCAL DEFINES SECTION                                                */
/* ============================================================================= */
#define USE_OLED_1106


/* ============================================================================= */
/* EEPROM GLOBALS&DEFINES SECTION                                                */
/* ============================================================================= */
#include "auralys_eeprom.h"


/* ============================================================================= */
/* EXTERNAL libaries                                                             */
/* ============================================================================= */

/* display lib */
#ifdef USE_OLED_1106
#include <Adafruit_GFX.h>
#include <Adafruit_SH110X.h>

#define SCREEN_I2C_ADDR (0x3c)
#define SCREEN_WIDTH     (128)
#define SCREEN_HEIGHT     (64)
#define OLED_RESET        (-1)

const char DISPLAY_HW_UNIT_TYPE[] = { 'N', 'L', 'R', 'F', 'S', 'T' };

Adafruit_SH1106G display = Adafruit_SH1106G(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET);
#endif

/* rtc */
#include "ESP32Time.h"

/* ============================================================================= */
/* BSP GLOBALS&DEFINES SECTION                                                   */
/* ============================================================================= */
#define BSP_CPU_MHZ_MIN                                                        (10) // 10Mhz is the lowest
#define BSP_CPU_MHZ_MAX                                                       (240) // 240Mhz is the max for ESP32
#define BSP_CPU_MHZ_DEFAULT                                                   (240)

#define BSP_BTN0_00                                                             (0) // use 0 for old prototypes
#define BSP_BTN0_09                                                             (9)
#define BSP_BTN0_12                                                            (12)

#define BSP_RETRY_MAX                                                           (3)

#define BSP_DELAY_3MS                                                           (3)

/* CPU speed control */
uint32_t bspCpuMhzCurrent = BSP_CPU_MHZ_DEFAULT;
uint32_t bspCpuMhzPrevious = BSP_CPU_MHZ_DEFAULT;
uint64_t bspChipID = 0;

/* loop control */
unsigned long bspWakeUpMillis = 0;

/* display status message */
char bspDisplayCtrlMsg[64];

char bspDisplayLogMsg[2][21];
bool bspDisplayLogMsgIdx = 0;

bool bspDisplayCtrlFullscreen = false;
uint8_t bspDisplayCtrlTimeout = 0;

///* buttons control */
// volatile uint8_t bsp_btn0 = 0;
// volatile uint8_t bsp_btn0_gpio = BSP_BTN0_00;
// volatile uint8_t bsp_buz0_gpio = BSP_BUZ0_16;



/* configuration type (only DEFAULT) */
// uint8_t bspConfig = BSP_CONFIG_DEFAULT;

/* this is the eeprom variable to detect if the hw has been initialized once */
uint8_t bspInitialized = 0;
uint8_t bspActivated = 0;



/* ============================================================================= */
/* WiFi & BT GLOBALS&DEFINES SECTION                                             */
/* ============================================================================= */

/* variable used with WiFiManager added for SSID/User/Pass select */
bool volatile wifi_enabled = true;
bool volatile wifi_connected = false;


/* HTTP firmware Update */
#define HTTPUPDATE_RD_SERVER "ilbert-labs.duckdns.org"
/* note: production server same as R&D until we have a production server running */
// #define HTTPUPDATE_PRODUCTION_SERVER "www.brainworks.it"
#define HTTPUPDATE_PRODUCTION_SERVER "ilbert-labs.duckdns.org"

/* HTTP data upload */
#define HTTPSEND_RD_SERVER "ilbert-labs.duckdns.org"
/* note: production server same as R&D until we have a production server running */
// #define HTTPSEND_PRODUCTION_SERVER "www.brainworks.it"
#define HTTPSEND_PRODUCTION_SERVER "ilbert-labs.duckdns.org"

#define HTTPUPDATE_RETRY_MAX                                                    (5)
#define HTTPCONFIG_RETRY_MAX                                                    (3)
#define HTTPSEND_MAX_PAYLOAD_SIZE                                             (240)
#define HTTPSEND_MAX_PAYLOAD_ITEMS                                             (12) // 240/12
#define HTTPSEND_MIN_PAYLOAD_ITEMS                                              (6)
#define HTTPSEND_MIN_PAYLOAD_SIZE   ((EE_SECTION_EFSLOG_ITEM_SIZE - 1) * HTTPSEND_MIN_PAYLOAD_ITEMS)

/* HTTP data buffer */
const uint32_t wifiConnectTimeoutMs = 7000;
const long httpTimeoutTime2S = 5000;
unsigned long httpCurrentTime = millis();
unsigned long httpPreviousTime = 0;

RTC_DATA_ATTR bool httpUpdate_flag = false;
RTC_DATA_ATTR bool httpConfig_flag = false;

WiFiServer server(80);

WiFiClient client;
String header;

// web command defines
#define CTRL_CMD_NONE            (0)
#define CTRL_CMD_STOP            (1)
#define CTRL_CMD_POSITION_GET    (2)
#define CTRL_CMD_POSITION_SET    (3)
#define CTRL_CMD_SPEED_GET       (4)
#define CTRL_CMD_SPEED_SET       (5)
#define CTRL_CMD_ACCEL_GET       (6)
#define CTRL_CMD_ACCEL_SET       (7)
#define CTRL_CMD_RESET           (8)
#define CTRL_CMD_REBOOT          (9)
#define CTRL_CMD_MKS_RESET      (10)
#define CTRL_CMD_STATUS_GET     (11)
#define CTRL_CMD_ZERO_SET       (12)
#define CTRL_CMD_GO_ZERO        (13)
#define CTRL_CMD_MINMAX_SET     (14)
#define CTRL_CMD_UNIT_TYPE_SET  (15)


/* ============================================================================= */
/* NTP Time GLOBALS&DEFINES SECTION                                               */
/* ============================================================================= */
// #include "EasyNTPClient.h"
// WiFiUDP udp;
// EasyNTPClient ntpClient(udp, "pool.ntp.org", ((1 * 60 * 60) + (0 * 60))); // CET = GMT + 5:30

/* ============================================================================= */
/* RTC GLOBALS&DEFINES SECTION                                                   */
/* ============================================================================= */

RTC_DATA_ATTR bool rtcTimeSynced_flag = false;

ESP32Time esp32_rtc(0);

///* EU CET Eastern Time Zone (Rome) */
// TimeChangeRule myDST = { "CST", Last, Sun, Mar, 2, +120 };
// TimeChangeRule mySTD = { "CET", Last, Sun, Oct, 3, +60 };

///* UTC TimeZone is the default for "Auralys" */
// Timezone myTZ(myDST, mySTD);

// TimeChangeRule* tcr;

/* ============================================================================= */
/* RGB LED GLOBALS&DEFINES SECTION                                               */
/* ============================================================================= */
#include <Adafruit_NeoPixel.h>

uint32_t ledRgbColorCurrent = 0;
uint32_t ledRgbColorPrevious = 0;

#define LED_RGB_RED                                    ((uint32_t) (0x50000000))
#define LED_RGB_VIOLET                                 ((uint32_t) (0x50005000))
#define LED_RGB_BLUE                                   ((uint32_t) (0x00005000))
#define LED_RGB_YELLOW                                 ((uint32_t) (0x50500000))
#define LED_RGB_GREEN                                  ((uint32_t) (0x00500000))

#define LED_GRB_GREEN                                  ((uint32_t) (0x50000000))
#define LED_GRB_VIOLET                                 ((uint32_t) (0x00505000))
#define LED_GRB_BLUE                                   ((uint32_t) (0x00005000))
#define LED_GRB_YELLOW                                 ((uint32_t) (0x50500000))
#define LED_GRB_RED                                    ((uint32_t) (0x00500000))

#define LED_RGB_OFF                                                        (0x0)
#define LED_RGB_WHITE                                  ((uint32_t) (0x50505000))
#define LED_DELAY_FAST                                                     (100)
#define LED_DELAY_SLOW                                                    (1000)

/* default colors to RGB mapping, will be changed if needed by the hwconfig */
uint32_t ledRgbColorRed = LED_RGB_RED;
uint32_t ledRgbColorGreen = LED_RGB_GREEN;
uint32_t ledRgbColorBlue = LED_RGB_BLUE;
uint32_t ledRgbColorViolet = LED_RGB_VIOLET;
uint32_t ledRgbColorYellow = LED_RGB_YELLOW;
uint32_t ledRgbColorWhite = LED_RGB_WHITE;
uint32_t ledRgbColorOff = LED_RGB_OFF;


/* ***************************************************************************** */
/*  MKS MOTOR GLOBALS & DEFINES SECTION                                          */
/* ***************************************************************************** */
#define MKS_BUFFER_SIZE (32)
uint8_t txBuffer[MKS_BUFFER_SIZE]; // send data array
uint8_t rxBuffer[MKS_BUFFER_SIZE]; // Receive data array
uint8_t rxCnt = 0; // Receive data count

uint8_t mksMotorSlaveAddr = 0x01;

int32_t mksMotorMax = (163840 * 10);
int32_t mksMotorMin = (-163840 * 10);
uint16_t mksMotorSpeed = 250;
uint16_t mksMotorAccel = 3;
volatile int64_t mksMotorEncoder = 0;
bool mksMotorDirCW = true;

typedef struct mksMotorCmd_ {
    int8_t status;
    int8_t command;
    int32_t parami_01;
    int32_t parami_02;
    float paramf_01;
    float paramf_02;
}mksMotorCmd_t;

mksMotorCmd_t mksMotorCmdQueue[1] = { 0 };

#define MKS_MOTOR_STATUS_ERROR   (-1)
#define MKS_MOTOR_STATUS_IDLE     (0)
#define MKS_MOTOR_STATUS_BUSY     (1)
#define MKS_MOTOR_STATUS_EXEC     (2)



/* ============================================================================= */
/* MOTION (ACCELEROMETER) GLOBALS&DEFINES SECTION                                */
/* ============================================================================= */
#include <LIS3DSH.h>

#define LIS3DSH_ADDR (0x1D) /// Default address is 0x19, ALT is 0x18

#define  MOTION_G_FORCE                                         ((float) (9.8066))
#define  MOTION_X_AXIS                                                         (0)
#define  MOTION_Y_AXIS                                                         (1)
#define  MOTION_Z_AXIS                                                         (2)
#define  MOTION_NO_AXIS                                                        (3)
#define  MOTION_RETRY_CNT_1S                                                (1000)

#define MOTION_SENSITIVITY_2G (0.060f) // mg/LSB
#define MG_TO_MS2 (0.00980665f)

LIS3DSH sensMotion;

volatile float acc_x, acc_y, acc_z;

bool sensMotionEnabled = false;



/*
 *
 * MAIN
 *
 */


/* ***************************************************************************** */
/*  ISRs & UTILS                                                                 */
/* ***************************************************************************** */





/* ***************************************************************************** */
/*  SETUP                                                                        */
/* ***************************************************************************** */

void setup()
{
    /* loop cycle control */
    bspWakeUpMillis = millis();

    Wire.begin(I2S_SDA_PIN, I2S_SCL_PIN);
    ledRgbSetup();

#ifdef DEBUG
    /* serial port debugging will take a lot of ram */
    Serial.begin(115200);
    delay(300);
    Serial.println("\n\n\n");
    Serial.println("*********************************");
    Serial.println("AuralysSpeaker (c)2025 | UniMore ");
    Serial.println("*********************************");
    Serial.print("ver. ");
    Serial.print(SW_VER_MJR); Serial.print(".");
    Serial.print(SW_VER_MIN); Serial.print(".");
    Serial.println(SW_VER_REV);
    Serial.println("*********************************");
    Serial.printf("CHIP MAC: %012llx\r\n", ESP.getEfuseMac());
    Serial.printf("CHIP MAC: %012llx\r\n", ESP.getChipModel());
    Serial.println("*********************************");
    Serial.println("\r\n\r\n\r\n");

#if 0
    while( !Serial )
    {
        ; // wait for serial port to connect. Needed for native USB port only
    }
#endif
#endif

    eepromSetup();

    // Display splash screen
    displaySetup();
    displaySplashScreen();
    delay(2000);
    displayClear();

    // Setup platform and check for WiFi Manager connection
    bspSetup();

    displayCtrlMsg((char*) "NTP Connect..");
    displayLoop();
    ntpSetup();
    displayClearCtrlMsg();
    displayLoop();
    ledRgbSetColor(ledRgbColorOff);

    // Start the MKS serial port
    mksSetup();

    /*
     * FW UPDATE
     *
     * This will happen only at boot.
     */
    ledRgbSetColor(ledRgbColorViolet);
    displayCtrlMsg((char*) "Check FW Update..");
    displayLoop();
    if( !httpUpdate_flag )
    {
        httpUpdateInit();
        httpUpdateLoop();
    }
    displayClearCtrlMsg();
    displayLoop();
    ledRgbSetColor(ledRgbColorOff);

    /* fire up the http server */
    displayCtrlMsg((char*) "Run WebServer..");
    httpServerSetup();

    /* motion sensor */
    motionSetup();

    // bspI2CScan();

    /*
       spawn display refresh on a separate core
     */
    xTaskCreatePinnedToCore(
        &displayRefresh, // <--- <our function name
        "displayRefresh", // <--- just some string for identification
        20000, // <--- this is important - reserve enough stack otherwise strane things will happen
        NULL, // <---- you can use this if you want to pass parameter to task function, NULL otherwise
        0, // <--- 1 = normal priority, 0 = low priority, 2 = high priority
        NULL, // <--- you probabbly don't need this (from what you have described)
        0); // <--- core: 0 or 1 (Arduino by default runs its code on core 1)


    /*
       spawn motor Queue refresh on a separate core
     */
    xTaskCreatePinnedToCore(
        &motorQueueRefresh, // <--- <our function name
        "motorQueueRefresh", // <--- just some string for identification
        20000, // <--- this is important - reserve enough stack otherwise strane things will happen
        NULL, // <---- you can use this if you want to pass parameter to task function, NULL otherwise
        1, // <--- 1 = normal priority, 0 = low priority, 2 = high priority
        NULL, // <--- you probabbly don't need this (from what you have described)
        1); // <--- core: 0 or 1 (Arduino by default runs its code on core 1)

    displayCtrlMsg((char*) "Ready...");
}

/* running display loop on a separate core of S3 */
void displayRefresh(void* param)
{
    /* this is launched in a separate FreeRTOS task */
    /* needs to be encapsulated in a while(1) loop */
    while( 1 )
    {
        motionLoop();
        displayLoop();
        yield();
        delay(300);
// #ifdef DEBUG
// Serial.print("displayRefresh() running on core ");
// Serial.println(xPortGetCoreID());
// #endif
    }
}

/* running display loop on a separate core of S3 */
void motorQueueRefresh(void* param)
{
    while( 1 )
    {
        mksLoop();
        yield();
        delay(100);
    }
}

/* main loop */
void loop()
{
    bspLoop();
    ntpLoop();
    httpServerLoop();
}
