/*
 *
 *    _  _   _ ___    _   _ __   _____     __  ___ _____
 *   /_\| | | | _ \  /_\ | |\ \ / / __|   / / | _ \_   _|
 *  / _ \ |_| |   / / _ \| |_\ V /\__ \  / /  |   / | |
 * /_/ \_\___/|_|_\/_/ \_\____|_| |___/ /_/   |_|_\ |_|
 *
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

/* libraries to be installed:
 * I2C Slave -> TinyWiresS: https://github.com/nadavmatalon/TinyWireS
 */

#include <Arduino.h>

#if defined( __AVR_ATtiny841__ )
// #define F_CPU 16000000                      // clock speed: 16MHz (external crystal)
    #include <WireS.h>                          // I2C library for ATtiny841 (and other modern ATtinys)
#else
// #define F_CPU 20000000                      // clock speed: 20MHz (external crystal)
    #include <TinyWireS.h>                      // I2C library for ATtiny84A (and other older ATtinys)
#endif

#include <PinChangeInterrupt.h>

/* ============================================================================= */
/* SOFTWARE REVISION GLOBALS&DEFINES SECTION                                     */
/* ============================================================================= */
#define BRWS_SW_PLATFORM_SIZE_MAX ( 16 )
#define BRWS_SW_PLATFORM  "brws"
#define BRWS_SW_CODENAME_SIZE_MAX ( 8 )
#define BRWS_SW_CODENAME  "rtencode"

/* Software Revision - BEGIN */
#define SW_VER_MJR    ( 1 ) /* NOTE: 0->255, 1byte coded */
#define SW_VER_MIN    ( 0 ) /* NOTE: 0->15,   4bit coded */
#define SW_VER_REV    ( 0 ) /* NOTE: 0->3,    2bit coded */

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
    #define LOG_MSG( ... )        { Serial.print( __VA_ARGS__ ); }
    #define LOG_MSGLN( ... )      { Serial.println( __VA_ARGS__ ); }
    #define LOG_PRINTF( ... )     { Serial.printf( __VA_ARGS__ ); }
    #define LOG_PRINTFLN( ... )   { Serial.printf( __VA_ARGS__ ); Serial.printf( "\n" ); }

    #ifdef QA
        #define SW_VER_BUILD  ( 3 )
    #else
        #define SW_VER_BUILD  ( 1 )
    #endif
#else
    #define LOG_MSG( ... )      /* blank */
    #define LOG_MSGLN( ... )    /* blank */
    #define LOG_PRINTF( ... )   /* blank */
    #define LOG_PRINTFLN( ... ) /* blank */
    #ifdef QA
        #define SW_VER_BUILD  ( 2 )
    #else
        #define SW_VER_BUILD  ( 0 )
    #endif
#endif
/* Software Revision - END */


/* ============================================================================= */
/* DEFINES                                                                       */
/* ============================================================================= */
#define I2C_SLAVE_ADDRESS ( 0x6A )  // Address of the slave
#define ID_LEN               ( 2 )
#define CMD_LEN              ( 1 )
#define ENCODER_PAYLOAD      ( 6 )
#define MAX_TRANSMISSION  ( 1 + ID_LEN + CMD_LEN + ENCODER_PAYLOAD )

/* this is to define the API version for supported commands/effects */
#define API_VER_MJR ( 0 )
#define API_VER_MIN ( 0 )

/*
 *
 * ATMEL ATTINY84 / ARDUINO
 *
 +-\/-+
 *                    VCC  1|    |14  GND
 *            (D 10)  PB0  2|    |13  AREF (D  0)
 *            (D  9)  PB1  3|    |12  PA1  (D  1)
 *                    PB3  4|    |11  PA2  (D  2)
 * PWM  INT0  (D  8)  PB2  5|    |10  PA3  (D  3)
 * PWM        (D  7)  PA7  6|    |9   PA4  (D  4)
 * PWM        (D  6)  PA6  7|    |8   PA5  (D  5)     PWM
 +----+
 * IDE Attiny84 Physical Pin
 * 0      PA0           13
 * 1      PA1           12
 * 2      PA2           11
 * 3      PA3           10
 * 4      PA4            9
 * 5      PA5            8
 * 6      PA6            7
 * 7      PA7            6
 * 8      PB2            5
 * 9      PB1            3
 * 10      PB0            2
 *
 */

/* INPUT / interrupt pins */
#define pinSwitchR  ( PA0 )
#define pinSwitchC  ( PA1 )
#define pinSwitchL  ( PA2 )
#define pinEncoderA   ( 8 ) // PB2
#define pinEncoderB  ( 10 ) // PB0

/* OUTPUT pins */
#define pinOutSwitch  ( PA7 )
#define pinOutEncoder   ( 9 ) // PB1

enum cmd_type
{
    CMD_NONE=0,               // Make sure this item is always *first* in the enum!
    CMD_GET_STATUS,           // Make sure this item is always *first* in the enum!
    CMD_SET_ENCODER_OFFSET,
    CMD_SET_ENCODER_LIMIT,
    CMD_SET_DIVIDER,
    CMD_LAST                  // Make sure this item is always *last* in the enum!
};

/* ============================================================================= */
/* GLOBALS                                                                       */
/* ============================================================================= */

volatile uint8_t request[ MAX_TRANSMISSION ];   // incoming I2C data.
volatile uint8_t request_len = 0;
volatile uint8_t response[ MAX_TRANSMISSION ];  // outgoing I2C data.
volatile uint8_t response_len = 0;

volatile int32_t impulse_cnt = 0;

volatile uint8_t ctrl_flags = 0; // MSB is RESERVED
volatile uint8_t ctrl_flags_bkp = 0;

volatile uint8_t encoder_divider = 8;

volatile int AB_bkp = LOW;

volatile uint8_t rv = 0;

volatile bool handleCommand = false;


/* ============================================================================= */
/* fake mtx stuff                                                                */
/* ============================================================================= */

volatile bool fakeMTX = false;

void lockMtx( volatile bool* mtx )
{
    while ( true == *mtx )
    {
        delay( 1 );
    }

    *mtx = true;
}


void unlockMtx( volatile bool* mtx )
{
    *mtx = false;
}


/* ============================================================================= */
/* ISRs (we use them in polling mode due to the single INT0 being used by I2C Slave) */
/* ============================================================================= */

void isrSwitch( )
{
    uint8_t tmp8 = 0;
    int tmpL = ( !digitalRead( pinSwitchL ) ) & 0x01;
    int tmpC = ( !digitalRead( pinSwitchC ) ) & 0x01;
    int tmpR = ( !digitalRead( pinSwitchR ) ) & 0x01;

    tmp8 = ctrl_flags;
    tmp8 &= 0b11110001;
    tmp8 |= ( tmpL << 3 ) + ( tmpC << 2 ) + ( tmpR << 1 );

    lockMtx( &fakeMTX );
    ctrl_flags = tmp8;
    // ctrl_flags &= 0b11110001;
    // ctrl_flags |= ( tmpL << 3 ) + ( tmpC << 2 ) + ( tmpR << 1 );
    unlockMtx( &fakeMTX );

    // on change
    if ( ctrl_flags_bkp != ctrl_flags )
    {
        ctrl_flags_bkp = ctrl_flags;
        digitalWrite( pinOutSwitch, !digitalRead( pinOutSwitch ) );
    }
}


void isrEncoder( )
{
    int tmpA = digitalRead( pinEncoderA );
    int tmpB = digitalRead( pinEncoderB );

    // rising
    if ( ( LOW == AB_bkp ) && ( HIGH == tmpA ) )
    {
        if ( LOW == tmpB )
        {
            impulse_cnt++;
            lockMtx( &fakeMTX );
            ctrl_flags |= ( 1 << 0 );
            unlockMtx( &fakeMTX );
        }
        else
        {
            impulse_cnt--;
            lockMtx( &fakeMTX );
            ctrl_flags &= ~( uint8_t( 1 << 0 ) );
            unlockMtx( &fakeMTX );
        }
    }

    if ( AB_bkp != tmpA )
    {
        AB_bkp = tmpA;
    }

    if ( impulse_cnt % encoder_divider )
    {
        digitalWrite( pinOutEncoder, !digitalRead( pinOutEncoder ) );
    }
}


void i2cReceive( uint8_t n )
{
    if ( n > MAX_TRANSMISSION )
    {
        n = MAX_TRANSMISSION;
    }
    for (uint8_t i = 0; i < n; i++)
    {
        if ( TinyWireS.available( ) )
        {
            request[ i ] = TinyWireS.read( );
            request_len = i + 1;
        }
        else
        {
            break;
        }
    }

    while ( TinyWireS.available( ) )
    {
        TinyWireS.read( );
    }

    handleCommand = true;
    rv = request_len;
}


void i2cRequest( )
{
#if 1
    // write rv
    TinyWireS.write( rv );

    // write status
    TinyWireS.write( ctrl_flags );

    // write position
    TinyWireS.write( (uint8_t) ( ( impulse_cnt >> 24 ) & 0xFF ) );
    TinyWireS.write( (uint8_t) ( ( impulse_cnt >> 16 ) & 0xFF ) );
    TinyWireS.write( (uint8_t) ( ( impulse_cnt >> 8 ) & 0xFF ) );
    TinyWireS.write( (uint8_t) ( ( impulse_cnt >> 0 ) & 0xFF ) );
#else
    /* I/O loop to verify I2C transaction */
    uint8_t* tmp8 = (uint8_t*) &request[ 0 ];
    TinyWireS.write( *tmp8 );
    tmp8++;
    TinyWireS.write( *tmp8 );
    tmp8++;
    TinyWireS.write( *tmp8 );
    tmp8++;
    TinyWireS.write( *tmp8 );
    tmp8++;
    TinyWireS.write( *tmp8 );
    tmp8++;
    uint8_t a = 33;
    TinyWireS.write( a );
    tmp8++;
#endif
}


/* *************************************************************************** */
/* SETUP & MAIN                                                                */
/* *************************************************************************** */

void setup( )
{
    delay( 100 );
    TinyWireS.begin( I2C_SLAVE_ADDRESS );
    TinyWireS.onRequest( i2cRequest );
    TinyWireS.onReceive( i2cReceive );
    delay( 100 );
    pinMode( pinSwitchR,    INPUT_PULLUP );
    pinMode( pinSwitchL,    INPUT_PULLUP );
    pinMode( pinSwitchC,    INPUT_PULLUP );
    // pinMode( pinEncoderA, INPUT_PULLUP );
    // pinMode( pinEncoderB, INPUT_PULLUP );
    pinMode( pinOutEncoder, OUTPUT );
    pinMode( pinOutSwitch,  OUTPUT );
    delay( 100 );

    // attachPCINT( digitalPinToPCINT( pinSwitchR ),  isrSwitch, CHANGE );
    // attachPCINT( digitalPinToPCINT( pinSwitchL ),  isrSwitch, CHANGE );
    // attachPCINT( digitalPinToPCINT( pinSwitchC ),  isrSwitch, CHANGE );
    // attachPCINT( digitalPinToPCINT( pinEncoderA ), isrEncoder, RISING );
    // attachInterrupt(digitalPinToInterrupt(pinEncoderA), isrEncoder, RISING);
    // attachInterrupt(0, isrEncoder, RISING);

    impulse_cnt = 0;
    ctrl_flags = 0;
    ctrl_flags_bkp = 0;
    AB_bkp = 0;
}


/*
 * Request byte syntax
 * ========================
 * byte 0: REGISTER ADDR
 * byte 1: API MJR NUM
 * byte 2: API MIN NUM
 * byte 3: CMD
 */
void loop( )
{
    if ( handleCommand )
    {
        handleCommand = false;

        /* CHECK LEN: REGISTER, API and CMD always needed */
        if ( request_len >= 4 )
        {
            /* CHECK REGISTER */
            if ( request[ 0 ] == 0 )
            {
                /* CHECK API (16bit) */
                if ( ( request[ 1 ] == API_VER_MJR ) && ( request[ 2 ] == API_VER_MIN ) )
                {
                    /* CHECK COMMAND (16bit) */
                    switch ( request[ 3 ] )
                    {
                        case CMD_GET_STATUS:
                            rv = 0; // confirm command accepted
                            break;

                        case CMD_SET_ENCODER_OFFSET:
                            impulse_cnt = 0;
                            rv = 0; // confirm command accepted
                            break;

                        case CMD_SET_ENCODER_LIMIT:
                            rv = 0; // confirm command accepted
                            break;

                        case CMD_SET_DIVIDER:
                            encoder_divider = request[ 4 ];
                            rv = 0; // confirm command accepted
                            break;
                    }
                }
            }
        }
    }

    isrSwitch( );
    isrEncoder( );

    // This needs to be here
    TinyWireS_stop_check( );
}
