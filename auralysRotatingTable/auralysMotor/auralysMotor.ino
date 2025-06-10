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

#include <Wire.h>
#include <ArduinoJson.h>
#include <WiFi.h>

/* ============================================================================= */
/* SOFTWARE REVISION GLOBALS&DEFINES SECTION                                     */
/* ============================================================================= */
#define BRWS_SW_PLATFORM_SIZE_MAX ( 16 )
#define BRWS_SW_PLATFORM  "brws"
#define BRWS_SW_CODENAME_SIZE_MAX ( 8 )
#define BRWS_SW_CODENAME  "auralmtr"

/* Software Revision - BEGIN */
#define SW_VER_MJR    ( 1 ) /* NOTE: 0->255, 1byte coded */
#define SW_VER_MIN    ( 1 ) /* NOTE: 0->15,   4bit coded */
#define SW_VER_REV    ( 0 ) /* NOTE: 0->3,    2bit coded */

/* switch define for debug/release + qa build type */
// #define DEBUG
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


// Replace with your network credentials
const char*      ssid = "REPLACE_WITH_YOUR_SSID";
const char*      password = "REPLACE_WITH_YOUR_PASSWORD";

// Set web server port number to 80
const char*      hostname = "rtable";
WiFiServer server( 80 );

WiFiClient       client;
String           header;

// web command defines
#define CTRL_CMD_NONE         ( 0 )
#define CTRL_CMD_STOP         ( 1 )
#define CTRL_CMD_POSITION_GET ( 2 )
#define CTRL_CMD_POSITION_SET ( 3 )
#define CTRL_CMD_SPEED_GET    ( 4 )
#define CTRL_CMD_SPEED_SET    ( 5 )

// encoder / Attiny84
#define ENCODER_TX_LEN ( 4 )
#define ENCODER_RX_LEN ( 6 )
#define ENCODER_I2C_BUS_SPEED ( 100000 )
#define ENCODER_TABLE_ONETURN_COUNT ( 6000.0f )
byte             encoderDeviceAddress = 0x6A; // 0x0B

// motion control defines
#define MOTOR_L_EN ( 4 )
#define MOTOR_R_EN ( 5 )
#define MOTOR_L_PWM ( 32 )
#define MOTOR_R_PWM ( 33 )
#define MOTOR_SPEED_PWM_DEFAULT ( 50 )
#define MOTOR_SPEED_PWM_MIN ( 35 )
#define MOTOR_SPEED_PWM_MAX ( 255 )
#define DISTANCE_SPEED_MAX ( 90 )
#define SPEED_TAIL ( 5 )
#define MOTOR_SPEED_POSITIONS_LEN ( 5 )
int16_t          speed_positions[ MOTOR_SPEED_POSITIONS_LEN ] = { 0 };
volatile uint8_t speed_positions_idx = 0;

/* motion status register */
volatile uint8_t motion_status_ctrl = 0;
/* bit 0: stop / moving   */
#define MOTION_STATUS_CTRL_MOVING    ( 1 << 0 )
/* bit 1: anti-clockwise/clockwise turn */
#define MOTION_STATUS_CTRL_DIRECTION_CCW ( 1 << 1 )


// position sensord efines
#define POSITION_SENS_ENABLED ( 1 )
#define POSITION_NOT_VALID ( 0x7FFF )
volatile int16_t position = 0;
volatile int16_t position_begin = 0;
volatile int16_t position_end = 0;

#define POSITION_SAFEZONE_SPAN ( 32 )
#define POSITION_SAFEZONE_SIZE ( 2 * POSITION_SAFEZONE_SPAN + 1 )
int16_t          position_safezone[ POSITION_SAFEZONE_SIZE ] = { 0 };  // middle is target position
volatile bool    position_safezone_flag = false;
volatile bool    position_safezone_direction = false;
volatile bool    position_init_flag = false;

#define POSITIONS_HIST_LEN ( 8 )
int16_t          positions[ POSITIONS_HIST_LEN ] = { 0 };
volatile uint8_t positions_idx = 0;


// Loop Control variable, time and cycle count
const long       timeoutTime = 2000;
unsigned long    currentTime = millis( );
unsigned long    previousTime = 0;
int              count = 0;

volatile uint8_t motion_speed = 0;

/* ************************************************************************** */
/* Logging Functions                                                          */
/* ************************************************************************** */

void log_header( )
{
    LOG_MSGLN( "\r\n\r\n" );
    LOG_MSGLN( "*********************************" );
    LOG_MSGLN( "AuralysMotor (c)2025 | UniMore " );
    LOG_MSGLN( "*********************************" );
    LOG_MSG( "ver. " );
    LOG_MSG( SW_VER_MJR );
    LOG_MSG( "." );
    LOG_MSG( SW_VER_MIN );
    LOG_MSG( "." );
    LOG_MSGLN( SW_VER_REV );
    LOG_MSGLN( "*********************************" );
    LOG_PRINTF( "CHIP MAC: %012llx\r\n", ESP.getEfuseMac( ) );
    LOG_PRINTF( "CHIP MAC: %012llx\r\n", ESP.getChipModel( ) );
    LOG_MSGLN( "*********************************" );
    LOG_MSGLN( "\r\n\r\n" );
}


void log_footer( )
{
    LOG_MSG( "POSITION: (" );
    LOG_MSG( position );
    LOG_MSGLN( ") : " );
    LOG_MSGLN( "init done." );
    LOG_MSGLN( "************************************" );
}


/* ************************************************************************** */
/* Tools                                                                      */
/* ************************************************************************** */


void i2cscan( )
{
    byte error, address;
    int  nDevices;

    Serial.println( "Scanning..." );

    nDevices = 0;
    for (address = 1; address < 127; address++ )
    {
        // The i2c_scanner uses the return value of
        // the Write.endTransmisstion to see if
        // a device did acknowledge to the address.
        Wire.beginTransmission( address );
        error = Wire.endTransmission( );

        if ( error == 0 )
        {
            Serial.print( "I2C device found at address 0x" );
            if ( address < 16 )
            {
                Serial.print( "0" );
            }
            Serial.print( address, HEX );
            Serial.println( "  !" );

            nDevices++;
        }
        else if ( error == 4 )
        {
            Serial.print( "Unknown error at address 0x" );
            if ( address < 16 )
            {
                Serial.print( "0" );
            }
            Serial.println( address, HEX );
        }
    }
    if ( nDevices == 0 )
    {
        Serial.println( "No I2C devices found\n" );
    }
    else
    {
        Serial.println( "done\n" );
    }
}


/* ************************************************************************** */
/* Position Control Functions                                                 */
/* ************************************************************************** */

void position_init( )
{
    // Initialize I2C and reset chip
    Wire.begin( );
    Wire.setClock( ENCODER_I2C_BUS_SPEED );

    if ( POSITION_SENS_ENABLED )
    {
        // nothing to do here
    }
}


int8_t sensor_read( int16_t* position, uint8_t* flags )
{
    int8_t   rv = -1;

    int16_t  pos = 0;

    int      i = 0;

    uint8_t  cmd[ ENCODER_TX_LEN ] = { 0, 0, 0, 1 };
    uint8_t  data[ ENCODER_RX_LEN ] = { 0 };

    uint8_t* tmp = NULL;

    tmp = &cmd[ 0 ];
    Wire.beginTransmission( encoderDeviceAddress );
    for (i = 0; i < ENCODER_TX_LEN; i++)
    {
        Wire.write( *tmp );
        tmp++;
    }
    Wire.endTransmission( false );


    tmp = &data[ 0 ];
    Wire.requestFrom( encoderDeviceAddress, ENCODER_RX_LEN );
    for (i = 0; i < ENCODER_RX_LEN; i++)
    {
        *tmp = Wire.read( );
        tmp++;
    }
    Wire.endTransmission( );

    /* sanity check */
    uint8_t  dataValid = data[ 0 ];
    for (i = 1; i < ENCODER_RX_LEN; i++)
    {
        dataValid &= data[ i ];
    }

    if ( dataValid != 255 )
    {
        int32_t tmp32 = ( ( (int32_t) data[ 2 ] ) << 24 ) | ( ( (int32_t) data[ 3 ] ) << 16 ) | ( ( (int32_t) data[ 4 ] ) << 8 ) | data[ 5 ];

        pos = int(round( (float) ( tmp32 * 1.0 ) / ( ENCODER_TABLE_ONETURN_COUNT / 360.0 ) ) );

        if ( NULL != position )
        {
            *position = pos;
        }

        if ( NULL != flags )
        {
            *flags = data[ 1 ];
        }

        // for (i = 0; i < RX_LEN; i++)
        // {
        //     Serial.print( data[ i ] );
        //     Serial.print( " " );
        // }
        // Serial.print( "|" );
        // Serial.print( pos );
        // Serial.print( "|" );
        // Serial.print( tmp32 );
        // Serial.println( );

        rv = 0;
    }

    return rv;
}


int16_t sensor_set_zero( )
{
    int16_t  pos = POSITION_NOT_VALID;

    int      i = 0;

    uint8_t  cmd[ ENCODER_TX_LEN ] = { 0, 0, 0, 2 };
    uint8_t  data[ ENCODER_RX_LEN ] = { 0 };

    uint8_t* tmp = NULL;

    tmp = &cmd[ 0 ];
    Wire.beginTransmission( encoderDeviceAddress );
    for (i = 0; i < ENCODER_TX_LEN; i++)
    {
        Wire.write( *tmp );
        tmp++;
    }
    Wire.endTransmission( false );

    tmp = &data[ 0 ];
    Wire.requestFrom( encoderDeviceAddress, ENCODER_RX_LEN );
    for (i = 0; i < ENCODER_RX_LEN; i++)
    {
        *tmp = Wire.read( );
        tmp++;
    }
    Wire.endTransmission( );

    return 0;
}


int16_t position_read( bool motion, bool direction )
{
    int16_t pos_bkp = position;
    int16_t pos = position;

    if ( POSITION_SENS_ENABLED )
    {
        if ( 0 == sensor_read( &pos, NULL ) )
        {
            return pos;
        }
        return pos_bkp;
    }
}


void position_set_zero( )
{
    volatile bool speed_slow_flag = false;
    uint8_t       position_flags = 0;
    int8_t        rv = 0;
    int           retry_cnt = 0;

    float         tmp_speed = MOTOR_SPEED_PWM_DEFAULT;
    float         tmp_speed_delta = 0.0;


    /* get a valid indication of current random position */
    int16_t       tmp16 = position_read( motion_status_ctrl & MOTION_STATUS_CTRL_MOVING, motion_status_ctrl & MOTION_STATUS_CTRL_DIRECTION_CCW );

    position = tmp16;
    position_begin = position;
    position_end = 0;

    /* reset sensor counter */
    retry_cnt = 10000;
    rv = sensor_read( &tmp16, NULL );
    while ( ( rv == 0 ) && ( 0 != tmp16 ) && ( retry_cnt > 0 ) )
    {
        retry_cnt--;

        rv = sensor_read( &tmp16, NULL );
        if ( 0 != rv )
        {
            tmp16 = -1;

            // reset bus
            Wire.end( );
            delay( 50 );
            Wire.begin( );
            delay( 50 );
        }
        else
        {
            sensor_set_zero( );
            delay( 50 );
            rv = sensor_read( &tmp16, NULL );
        }
    }

    /* SAFETY CHECK */
    if ( retry_cnt <= 0 )
    {
        LOG_MSG( "ERROR: cannot set sensor zero offset" );
        // ToDo: raise an error here (led? didplay?)
    }

    /* now the counter on he sensor is zero */
    position = 0;
    position_begin = 0;
    position_end = 0;

    /* start searching for zero position on the turntable */
    position_init_flag = true;

    while ( 0 != sensor_read( NULL, &position_flags ) )
    {
        delay( 50 );
    }

    /* are position switches triggered ? if not start turning..*/
    if ( 0 != ( position_flags & 0b00000110 ) )
    {
        // set moving state
        motion_status_ctrl |= MOTION_STATUS_CTRL_MOVING;

        // set direction
        motion_status_ctrl &= ~( MOTION_STATUS_CTRL_DIRECTION_CCW );
        motion_update_speed( MOTOR_SPEED_PWM_DEFAULT );

        /* keep turning until we trigger switches, increase/decrease speed if needed */
        retry_cnt = 0;
        while ( 0 != ( position_flags & 0b00000110 ) )
        {
            retry_cnt++;
            while ( 0 != sensor_read( NULL, &position_flags ) )
            {
                delay( 50 );
            }

            if ( false == speed_slow_flag )
            {
                if ( 0 == ( retry_cnt % 256 ) )
                {
                    // Serial.print( "UP " );
                    // Serial.print( tmp_speed );
                    // Serial.print( ": " );
                    // Serial.println( tmp_speed_delta );

                    if ( 0 == tmp_speed_delta )
                    {
                        tmp_speed_delta = ( (float) ( MOTOR_SPEED_PWM_MAX - tmp_speed ) / 50.0 );
                    }

                    tmp_speed = ( ( tmp_speed + tmp_speed_delta ) > MOTOR_SPEED_PWM_MAX )?( MOTOR_SPEED_PWM_MAX ):( tmp_speed + tmp_speed_delta );
                    motion_update_speed( round( tmp_speed ) );
                }
                if ( ( ~position_flags ) & 0b00000110 )
                {
                    speed_slow_flag = true;
                    tmp_speed_delta = 0;
                }
            }
            else
            {
                if ( 0 == ( retry_cnt % 256 ) )
                {
                    // Serial.println( "DOWN" );
                    // Serial.print( tmp_speed );
                    // Serial.print( ": " );
                    // Serial.println( tmp_speed_delta );

                    if ( 0 == tmp_speed_delta )
                    {
                        tmp_speed_delta = (uint8_t) ( (float) ( tmp_speed - MOTOR_SPEED_PWM_MIN ) / 10.0 );
                    }

                    tmp_speed = ( ( tmp_speed - tmp_speed_delta ) < MOTOR_SPEED_PWM_MIN )?( MOTOR_SPEED_PWM_MIN ):( tmp_speed - tmp_speed_delta );
                    motion_update_speed( round( tmp_speed ) );
                }
            }
        }

        /* magnets position require an offset correction of ~2 degree */
        retry_cnt = 10000;
        rv = sensor_read( &tmp16, NULL );
        while ( ( rv == 0 ) && ( 0 != tmp16 ) && ( retry_cnt > 0 ) )
        {
            retry_cnt--;

            rv = sensor_read( &tmp16, NULL );
        }

        while ( ( tmp16 - 1 ) < position_read( motion_status_ctrl & MOTION_STATUS_CTRL_MOVING, motion_status_ctrl & MOTION_STATUS_CTRL_DIRECTION_CCW ) )
        {
            delay( 50 );
        }

        /* we got in position, stop turning */
        motion_stop( );
        delay( 1000 );
    }

    /* redundant, reset sensor counter, again */
    retry_cnt = 10000;
    rv = sensor_read( &tmp16, NULL );
    while ( ( rv == 0 ) && ( 0 != tmp16 ) && ( retry_cnt > 0 ) )
    {
        retry_cnt--;

        rv = sensor_read( &tmp16, NULL );
        if ( 0 != rv )
        {
            tmp16 = -1;

            // reset bus
            Wire.end( );
            delay( 50 );
            Wire.begin( );
            delay( 50 );
        }
        else
        {
            sensor_set_zero( );
            delay( 50 );
            rv = sensor_read( &tmp16, NULL );
        }
    }

    /* SAFETY CHECK */
    if ( retry_cnt <= 0 )
    {
        LOG_MSG( "ERROR: cannot set sensor zero offset" );
        // ToDo: raise an error here (led? didplay?)
    }

    /* now the counter ont he sensor is zero */
    position = 0;
    position_begin = 0;
    position_end = 0;

    /* important: seed the speed history array for speed computation */
    for (int i = 0; i < MOTOR_SPEED_POSITIONS_LEN; i++)
    {
        speed_positions[ i ] = position;
    }

    position_init_flag = false;
}


void position_compute_safezone( int16_t target, bool force_compute )
{
    int16_t tmp16a = target;
    int16_t tmp16b = target;
    int16_t in, out;

    // safety window
    tmp16a = target;
    tmp16b = target;

    bool    position_safezone_direction_cpy = position_safezone_direction;

    if ( !( motion_status_ctrl & MOTION_STATUS_CTRL_MOVING ) )
    {
        LOG_MSGLN( "safezone - static" );
        position_safezone_direction = true;
        if ( position > target )
        {
            position_safezone_direction = false;
            LOG_MSGLN( "safezone- inverted" );
        }
    }
    else
    {
        LOG_MSGLN( "safezone - moving" );
        position_safezone_direction = true;
        if ( !( motion_status_ctrl & MOTION_STATUS_CTRL_DIRECTION_CCW ) )
        {
            position_safezone_direction = false;
            LOG_MSGLN( "safezone- inverted" );
        }
    }

    if ( ( !force_compute ) &&
         ( position_safezone[ POSITION_SAFEZONE_SPAN ] == target ) && ( position_safezone_direction_cpy == position_safezone_direction ) )
    {
        // safezone already computed!
        return;
    }

    position_safezone[ POSITION_SAFEZONE_SPAN ] = target;

    for (int i = 1; i <= POSITION_SAFEZONE_SPAN; i++)
    {
        tmp16a = ( tmp16a - 1 );
        // these are not needed since we added a proper encoder on the rotating table
        // tmp16a = ( tmp16a < 0 ) ? ( 360 + tmp16a ) : tmp16a;
        // tmp16a = ( tmp16a >= 360 ) ? ( tmp16a - 360 ) : tmp16a;
        in = tmp16a;

        tmp16b = ( tmp16b + 1 );
        // these are not needed since we added a proper encoder on the rotating table
        // tmp16b = ( tmp16b < 0 ) ? ( 360 + tmp16b ) : tmp16b;
        // tmp16b = ( tmp16b >= 360 ) ? ( tmp16b - 360 ) : tmp16b;
        out = tmp16b;

        // if stationary go by abs position
        if ( !( motion_status_ctrl & MOTION_STATUS_CTRL_MOVING ) )
        {
            if ( position > target )
            {
                int16_t tmp = in;
                in = out;
                out = tmp;
            }
        }
        else
        {
            if ( !( motion_status_ctrl & MOTION_STATUS_CTRL_DIRECTION_CCW ) )
            {
                int16_t tmp = in;
                in = out;
                out = tmp;
            }
        }

        position_safezone[ POSITION_SAFEZONE_SPAN - i ] = in;
        position_safezone[ POSITION_SAFEZONE_SPAN + i ] = out;
    }

    LOG_MSG( "[" );
    for (int i = 0; i < ( POSITION_SAFEZONE_SPAN ); i++)
    {
        LOG_MSG( position_safezone[ i ] );
        LOG_MSG( ", " );
    }
    LOG_MSG( "(" );
    LOG_MSG( position_safezone[ POSITION_SAFEZONE_SPAN ] );
    LOG_MSG( ") " );
    for (int i = POSITION_SAFEZONE_SPAN + 1; i < ( 2 * POSITION_SAFEZONE_SPAN + 1 ); i++)
    {
        LOG_MSG( position_safezone[ i ] );
        LOG_MSG( ", " );
    }

    LOG_MSGLN( "]" );
}


bool get_safezone_relative_position( int16_t current, int16_t* position_rel, int16_t* target_rel )
{
    bool    position_overshoot = false;
    int16_t target_position_idx = POSITION_SAFEZONE_SPAN + 1;

    if ( NULL != position_rel )
    {
        *position_rel = POSITION_NOT_VALID;
    }

    if ( NULL != target_rel )
    {
        *target_rel = POSITION_NOT_VALID;
    }

    if ( POSITION_NOT_VALID == current )
    {
        return position_overshoot;
    }

    position_safezone_flag = false;

    // now check for safezone position
    for (int i = 0; i < POSITION_SAFEZONE_SIZE; i++)
    {
        if ( current == position_safezone[ i ] )
        {
            // mark safety zone flag
            position_safezone_flag = true;

            // check for overshoot
            if ( i > ( target_position_idx + 1 ) )
            {
                LOG_MSG( "ERROR: get_position_relative: overshoot, " );
                LOG_MSG( i );
                LOG_MSG( " -> " );
                LOG_MSGLN( current );

                position_overshoot = true;
            }

            if ( NULL != position_rel )
            {
                *position_rel = i;
            }

            if ( NULL != target_rel )
            {
                *target_rel = target_position_idx;
            }
        }
    }

    return position_overshoot;
}


bool position_check_overshoot( int16_t current )
{
    bool position_overshoot = false;

    position_overshoot = get_safezone_relative_position( current, NULL, NULL );

    return position_overshoot;
}


void position_loop( )
{
    int16_t tmp16 = 0;

    int8_t  rv = 0;

    rv = sensor_read( &tmp16, NULL );

    if ( ( position != tmp16 ) && ( 0 == rv ) )
    {
        position = position_read( motion_status_ctrl & MOTION_STATUS_CTRL_MOVING,
                                  motion_status_ctrl & MOTION_STATUS_CTRL_DIRECTION_CCW );

        LOG_MSG( ",POS," );
        LOG_MSG( position );
        LOG_MSG( ",SPD," );
        LOG_MSGLN( motion_speed );
    }
    else if ( 0 == ( count % 1000 ) )
    {
        // periodic display
        LOG_MSG( "POS," );
        LOG_MSG( position );
        // LOG_MSG( sensor_read( ) );
        LOG_MSG( ",SPD," );
        LOG_MSG( motion_speed );
        LOG_MSGLN( " (ping)" );
    }
}


/* ************************************************************************** */
/* Motion Control Functions                                                   */
/* ************************************************************************** */
void motion_init( )
{
    // enable motor control
    pinMode( MOTOR_L_EN, OUTPUT );
    pinMode( MOTOR_R_EN, OUTPUT );

    digitalWrite( MOTOR_L_EN, HIGH );
    digitalWrite( MOTOR_R_EN, HIGH );
    analogWrite( MOTOR_R_PWM, 0 );
    analogWrite( MOTOR_L_PWM, 0 );
    motion_status_ctrl = 0;
}


void motion_update_speed( uint8_t speed )
{
    if ( speed == 0 )
    {
        analogWrite( MOTOR_R_PWM, 0 );
        analogWrite( MOTOR_L_PWM, 0 );
    }
    else
    {
        // update speed
        if ( motion_status_ctrl & MOTION_STATUS_CTRL_DIRECTION_CCW )
        {
            analogWrite( MOTOR_R_PWM, speed );
            analogWrite( MOTOR_L_PWM, 0 );
        }
        else
        {
            analogWrite( MOTOR_R_PWM, 0 );
            analogWrite( MOTOR_L_PWM, speed );
        }
    }
}


uint8_t motion_compute_speed( int16_t current, int16_t begin, int16_t end, bool skip_safezone_flag )
{
    uint8_t  speed = MOTOR_SPEED_PWM_MIN;

    uint16_t distance2end = 0;
    uint16_t distance2begin = 0;

    int16_t  speed2end = 0;
    int16_t  speed2begin = 0;

    int16_t  current_avg = 0;
    int16_t  current_rel = POSITION_NOT_VALID;
    int16_t  target_rel = POSITION_NOT_VALID;


    // from global value (current speed)
    speed = motion_speed;

    get_safezone_relative_position( current, &current_rel, &target_rel );

    if ( position_safezone_flag && ( !skip_safezone_flag ) )
    {
        speed = MOTOR_SPEED_PWM_MIN;
        if ( ( POSITION_NOT_VALID != current_rel ) && ( POSITION_NOT_VALID != target_rel ) && ( current_rel < target_rel ) )
        {
            speed2end = (uint16_t) ( ( (float) ( MOTOR_SPEED_PWM_MAX - MOTOR_SPEED_PWM_MIN ) / (float) DISTANCE_SPEED_MAX ) * ( target_rel - current_rel - SPEED_TAIL ) ) + MOTOR_SPEED_PWM_MIN;
            speed2end = ( MOTOR_SPEED_PWM_MIN > speed2end ) ? MOTOR_SPEED_PWM_MIN : speed2end;
            speed2end = ( MOTOR_SPEED_PWM_MAX < speed2end ) ? MOTOR_SPEED_PWM_MAX : speed2end;

            speed = (uint8_t) speed2end;
        }
    }
    else
    {
        // average positions
        speed_positions[ speed_positions_idx ] = current;
        speed_positions_idx = ( speed_positions_idx + 1 ) % MOTOR_SPEED_POSITIONS_LEN;
        for (int i = 0; i < MOTOR_SPEED_POSITIONS_LEN; i++)
        {
            current_avg += speed_positions[ i ];
        }
        current_avg = ( current_avg + ( MOTOR_SPEED_POSITIONS_LEN / 2 ) ) / MOTOR_SPEED_POSITIONS_LEN;
        current = current_avg;

        distance2end = ( end > current ) ? ( end - current ) : ( current - end );
        speed2end = (uint16_t) ( ( (float) ( MOTOR_SPEED_PWM_MAX - MOTOR_SPEED_PWM_MIN ) / (float) DISTANCE_SPEED_MAX ) * ( distance2end - SPEED_TAIL ) ) + MOTOR_SPEED_PWM_MIN;
        speed2end = ( MOTOR_SPEED_PWM_MIN > speed2end ) ? MOTOR_SPEED_PWM_MIN : speed2end;
        speed2end = ( MOTOR_SPEED_PWM_MAX < speed2end ) ? MOTOR_SPEED_PWM_MAX : speed2end;

        distance2begin = ( begin > current ) ? ( begin - current ) : ( current - begin );
        speed2begin = (uint16_t) ( ( (float) ( MOTOR_SPEED_PWM_MAX - MOTOR_SPEED_PWM_MIN ) / (float) DISTANCE_SPEED_MAX ) * distance2begin ) + MOTOR_SPEED_PWM_MIN;
        speed2begin = ( MOTOR_SPEED_PWM_MIN > speed2begin ) ? MOTOR_SPEED_PWM_MIN : speed2begin;
        speed2begin = ( MOTOR_SPEED_PWM_MAX < speed2begin ) ? MOTOR_SPEED_PWM_MAX : speed2begin;

        speed = (uint8_t) ( ( speed2begin < speed2end ) ? speed2begin : speed2end );
    }


    return speed;
}


void motion_stop( )
{
    uint16_t tmp16;

    // FULL STOP
    digitalWrite( MOTOR_L_EN, HIGH );
    digitalWrite( MOTOR_R_EN, HIGH );

    motion_status_ctrl &= ~( MOTION_STATUS_CTRL_MOVING );

    motion_update_speed( 0 );

    position_begin = position;
    position_end = position;

    position_safezone_flag = false;
}


void motion_loop( )
{
    uint8_t position_flags = 0;

    if ( position == position_end )
    {
        motion_stop( );

        if ( 0 == ( count % 10000 ) )
        {
            position = position_read( motion_status_ctrl & MOTION_STATUS_CTRL_MOVING, motion_status_ctrl & MOTION_STATUS_CTRL_DIRECTION_CCW );
        }

        /* if we are on posizion ZERO, check for zero-offset via sensor switches */
        if ( 0 == position )
        {
            while ( 0 != sensor_read( NULL, &position_flags ) )
            {
                delay( 50 );
            }

            /* are position switches triggered ? */
            if ( 0 != ( position_flags & 0b00000110 ) )
            {
                position_set_zero( );
            }
        }
    }
    else if ( !( motion_status_ctrl & MOTION_STATUS_CTRL_MOVING ) )
    {
        LOG_MSG( "motion: start, curr: " );
        LOG_MSG( position );
        LOG_MSG( " begin: " );
        LOG_MSG( position_begin );
        LOG_MSG( " end: " );
        LOG_MSGLN( position_end );

        position_begin = position;
        position_compute_safezone( position_end, false );

        // set moving state
        motion_status_ctrl |= MOTION_STATUS_CTRL_MOVING;

        // set direction
        if ( position < position_end )
        {
            LOG_MSGLN( "motion: start, CCW" )
            // turn counter-clockwise, positive azimuth
            motion_status_ctrl |= MOTION_STATUS_CTRL_DIRECTION_CCW;
            motion_update_speed( MOTOR_SPEED_PWM_MIN );
        }
        else
        {
            LOG_MSGLN( "motion: start, CW" )
            motion_status_ctrl &= ~( MOTION_STATUS_CTRL_DIRECTION_CCW );
            motion_update_speed( MOTOR_SPEED_PWM_MIN );
        }

        LOG_MSGLN( "motion: start, done" )
    }
    else if ( motion_status_ctrl & MOTION_STATUS_CTRL_MOVING )
    {
        motion_speed = motion_compute_speed( position, position_begin, position_end, false );

        motion_update_speed( motion_speed );

        // check position overshoot
        bool position_overshoot = position_check_overshoot( position );

        if ( position_overshoot )
        {
            if ( motion_status_ctrl & MOTION_STATUS_CTRL_DIRECTION_CCW )
            {
                LOG_MSGLN( "invert!!! counter-clockwise->clockwise" );
                motion_status_ctrl &= ~( MOTION_STATUS_CTRL_DIRECTION_CCW );

                // stop
                analogWrite( MOTOR_R_PWM, 0 );
                analogWrite( MOTOR_L_PWM, 0 );

                // pause
                delay( 1000 );
                // set begin & speed
                position_begin = position;

                // set safety
                position_compute_safezone( position_end, true );

                // invert motion: clockwise
                motion_speed = motion_compute_speed( position, position_begin, position_end, false );

                LOG_MSG( "invert speed:" );
                LOG_MSGLN( motion_speed );

                // set speed
                motion_update_speed( motion_speed );
                // analogWrite( MOTOR_R_PWM, 0 );
                // analogWrite( MOTOR_L_PWM, motion_speed );
            }
            else
            {
                LOG_MSGLN( "invert!!! clockwise->counter-clockwise" );
                motion_status_ctrl |= MOTION_STATUS_CTRL_DIRECTION_CCW;

                // stop
                analogWrite( MOTOR_R_PWM, 0 );
                analogWrite( MOTOR_L_PWM, 0 );

                // pause
                delay( 1000 );

                // set begin & speed
                position_begin = position;

                // set safety
                position_compute_safezone( position_end, true );

                // invert motion: counter-clockwise
                motion_speed = motion_compute_speed( position, position_begin, position_end, false );

                LOG_MSG( "invert speed:" );
                LOG_MSGLN( motion_speed );

                // set speed
                motion_update_speed( motion_speed );
                // analogWrite( MOTOR_R_PWM, motion_speed );
                // analogWrite( MOTOR_L_PWM, 0 );
            }
        }
    }
}


/* ************************************************************************** */
/* Webserver Control Functions                                                */
/* ************************************************************************** */

void webserver_init( )
{
    // Connect to Wi-Fi network with SSID and password
    WiFi.setHostname( hostname );
    LOG_MSG( "Connecting to " );
    LOG_MSGLN( ssid );
    WiFi.begin( ssid, password );
    while ( WiFi.status( ) != WL_CONNECTED )
    {
        delay( 500 );
        LOG_MSG( "." );
    }

    // Print local IP address and start web server
    LOG_MSGLN( "" );
    LOG_MSGLN( "WiFi connected." );
    LOG_MSGLN( "IP address: " );
    LOG_MSGLN( WiFi.localIP( ) );
    server.begin( );
}


void webserver_loop( )
{
    if ( WiFi.status( ) == WL_CONNECTED )
    {
        volatile uint8_t cmd_ctrl = CTRL_CMD_NONE;
        volatile int16_t cmd_ctrl_position = position_end;
        volatile int16_t req_content_length = -1;
        volatile int16_t header_content_length = -1;

        client = server.accept( );

        if ( client )
        {
            currentTime = millis( );
            previousTime = currentTime;
            req_content_length = -1;
            header_content_length = -1;

            LOG_MSGLN( "New Client." );

            String currentLine = "";
            while ( client.connected( ) && currentTime - previousTime <= timeoutTime )
            {
                currentTime = millis( );
                if ( client.available( ) )
                {
                    char c = client.read( );
// #ifdef DEBUG
//                     Serial.write( c );
// #endif
                    header += c;

                    if ( ( c == '\n' ) ||
                         ( ( header_content_length > 0 ) && ( header.length( ) >= header_content_length ) ) )
                    {
                        // if the byte is a newline character
                        // if the current line is blank, you got two newline characters in a row.
                        // that's the end of the client HTTP request, so send a response (if there is n payload)
                        if ( ( currentLine.length( ) == 0 ) &&
                             ( header.indexOf( "Content-Length:" ) >= 0 ) && ( req_content_length < 0 ) )
                        {
                            LOG_MSG( "Got content length = " );

                            String val = "";
                            for (int i = 16 + header.indexOf( "Content-Length: " ); i < header.length( ); i++ )
                            {
                                val += header.charAt( i );
                            }
                            LOG_MSGLN( val );

                            req_content_length = val.toInt( );
                            header_content_length = header.length( ) + req_content_length;
                        }
                        // if the byte is a newline character
                        // if the current line is blank, you got two newline characters in a row.
                        // that's the end of the client HTTP request, so send a response (if there is n payload)
                        else if ( ( ( header.indexOf( "Content-Length:" ) < 0 ) && ( currentLine.length( ) == 0 ) ) ||
                                  ( header.length( ) >= header_content_length ) )
                        {
                            cmd_ctrl = CTRL_CMD_NONE;

                            // HTTP headers always start with a response code (e.g. HTTP/1.1 200 OK)
                            // and a content-type so the client knows what's coming, then a blank line:
                            client.println( "HTTP/1.1 200 OK" );
                            client.println( "Content-type:text/html" );
                            client.println( "Connection: close" );
                            client.println( );

                            LOG_MSGLN( "===================================" );
                            LOG_MSGLN( "GOT HTTP CMD" );
                            LOG_MSGLN( header );

                            if ( ( header.indexOf( "GET /ctrl/stop" ) >= 0 ) || ( header.indexOf( "POST /ctrl/stop" ) >= 0 ) )
                            {
                                cmd_ctrl = CTRL_CMD_STOP;
                                LOG_MSGLN( "GET request for STOP!" );
                            }
                            else if ( header.indexOf( "GET /position/get" ) >= 0 )
                            {
                                cmd_ctrl = CTRL_CMD_POSITION_GET;
                                LOG_MSGLN( "GET request for get-position" );
                            }
                            else if ( header.indexOf( "POST /position/set" ) >= 0 )
                            {
                                cmd_ctrl = CTRL_CMD_POSITION_SET;

                                LOG_MSG( "POST request for set-position: " );

                                String post_param = "";
                                char   p;

                                // position is 0(min)->359(max)
                                p = header.charAt( header.length( ) - req_content_length + 0 );
                                post_param += p;
                                p = header.charAt( header.length( ) - req_content_length + 1 );
                                post_param += p;
                                p = header.charAt( header.length( ) - req_content_length + 2 );
                                post_param += p;

                                cmd_ctrl_position = post_param.toInt( );

                                // override if we are initializing
                                position_init_flag = false;

                                LOG_MSGLN( cmd_ctrl_position );
                            }

                            if ( !( header.indexOf( "json" ) ) )
                            {
                                // Display the HTML web page
                                client.println( "<!DOCTYPE html><html>" );
                                client.println( "<head><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">" );
                                client.println( "<link rel=\"icon\" href=\"data:,\">" );
                                // CSS to style the on/off buttons
                                // Feel free to change the background-color and font-size attributes to fit your preferences
                                // client.println("<style>html { font-family: Helvetica; display: inline-block; margin: 0px auto; text-align: center;}");
                                // client.println(".button { background-color: #4CAF50; border: none; color: white; padding: 16px 40px;");
                                // client.println("text-decoration: none; font-size: 30px; margin: 2px; cursor: pointer;}");
                                // client.println(".button2 {background-color: #555555;}</style></head>");
                                // Web Page Heading
                                client.println( "<body>" );
                            }
                            else if ( ( CTRL_CMD_POSITION_GET == cmd_ctrl ) || ( CTRL_CMD_SPEED_GET == cmd_ctrl ) || ( CTRL_CMD_STOP == cmd_ctrl ) )
                            {
                                JsonDocument reply;

                                if ( CTRL_CMD_STOP == cmd_ctrl )
                                {
                                    motion_stop( );
                                }
                                reply[ "syntax_ver" ] = "0.1";
                                reply[ "error" ] = 0;
                                reply[ "position" ] = position;
                                reply[ "position_begin" ] = position_begin;
                                reply[ "position_end" ] = position_end;
                                reply[ "motion" ] = motion_status_ctrl & 0x01;
                                reply[ "motion_direction" ] = ( motion_status_ctrl & 0x02 ) >> 1;
                                reply[ "motion_speed" ] = motion_speed; // motion_compute_speed (position, position_begin, position_end);

                                serializeJsonPretty( reply, client );
                            }
                            else if ( CTRL_CMD_POSITION_SET == cmd_ctrl )
                            {
                                JsonDocument reply;
                                reply[ "syntax_ver" ] = "0.1";
                                reply[ "error" ] = 1;
                                reply[ "position" ] = position;
                                reply[ "position_begin" ] = position_begin;
                                reply[ "position_end" ] = position_end;
                                reply[ "motion" ] = motion_status_ctrl & 0x01;
                                reply[ "motion_direction" ] = ( motion_status_ctrl & 0x02 ) >> 1;
                                reply[ "motion_speed" ] = motion_speed; // motion_compute_speed (position, position_begin, position_end);

                                if ( ( cmd_ctrl_position >= 0 ) && ( cmd_ctrl_position < 360 ) )
                                {
                                    // position_end = cmd_ctrl_position;
                                    reply[ "error" ] = 0;
                                    reply[ "position_end" ] = cmd_ctrl_position; // position_end;
                                }

                                serializeJsonPretty( reply, client );
                            }
                            else
                            {
                                JsonDocument reply;
                                reply[ "syntax_ver" ] = "0.1";
                                reply[ "error" ] = 1;
                                serializeJsonPretty( reply, client );
                            }

                            if ( !( header.indexOf( ".json" ) ) )
                            {
                                client.println( "</body></html>" );
                            }

                            // The HTTP response ends with another blank line
                            client.println( );
                            client.println( );

                            client.clear( );

                            // clear web request
                            header = "";

                            // disconnect client
                            //                            client.stop();

                            // Break out of the while loop
                            break;
                        }
                        else
                        { // if you got a newline, then clear currentLine
                            currentLine = "";
                        }
                    }
                    else if ( c != '\r' )
                    {                     // if you got anything else but a carriage return character,
                        currentLine += c; // add it to the end of the currentLine
                    }
                }
                else
                {
                    client.clear( );
                }
            }


            // UPDATE:
            // update end position if needed
            LOG_MSGLN( "web loop, done." )
            if ( ( cmd_ctrl_position != position_end ) &&
                 ( cmd_ctrl_position >= 0 ) &&
                 ( cmd_ctrl_position < 360 ) )
            {
                position_begin = position;
                position_end = cmd_ctrl_position;
                position_safezone_flag = false;
            }

            client.stop( );
        }
    }
}


/* ************************************************************************** */
/* Setup & MAIN                                                               */
/* ************************************************************************** */

void setup( )
{
#ifdef DEBUG
    Serial.begin( 115200 );

    delay( 2000 );

    int delay_cnt = 5000;
    while ( !Serial && delay_cnt-- )
    {
        delay( 1 );
    }
#endif

    log_header( );

    // webserver
    webserver_init( );

    // enable motor control
    motion_init( );
    motion_stop( );

    // position sensor
    position_init( );

    // we need a VALID initial position at boot
    position_set_zero( );

    log_footer( );

    // loop cycle count
    count = 0;
}


void loop( )
{
    count++;

    webserver_loop( );

    position_loop( );

    motion_loop( );
}
