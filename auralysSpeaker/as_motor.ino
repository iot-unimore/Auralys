/* ============================================================================= */
/* MKS MOTOR CONTROL                                                             */
/* ============================================================================= */

void mksSetup()
{
    Serial1.begin(UART_MKS_BAUD, SERIAL_8N1, UART_MKS_RX_PIN, UART_MKS_TX_PIN);

    /* TODO: set motor mode here, depending on the role of the unit */
    /*       closed loop for speaker, serial_vfoc for poles */
}

void mksLoop()
{
    uint8_t ackStatus;

    if( MKS_MOTOR_STATUS_BUSY == mksMotorCmdQueue[0].status )
    {
        switch( mksMotorCmdQueue[0].command )
        {
            case CTRL_CMD_STOP:
                LOG_MSGLN("mksLoop: CMD_STOP");
                displayCtrlMsgTemp((char*) "STOP!", 5);
                displayCtrlLogMsg((char*) "CMD_STOP, skip");
                mksMotorCmdQueue[0].status = MKS_MOTOR_STATUS_IDLE;
                break;

            case CTRL_CMD_POSITION_GET:
                LOG_MSGLN("mksLoop: GET_POSITION");
                displayCtrlMsgTemp((char*) "GET_POSITION", 5);
                displayCtrlLogMsg((char*) "GET_POS");

                mksMotorCmdQueue[0].status = MKS_MOTOR_STATUS_EXEC;

                ackStatus = getMksEncoderValue(mksMotorSlaveAddr);

                if( ackStatus == 0 )
                {
                    mksMotorCmdQueue[0].status = MKS_MOTOR_STATUS_ERROR;
                    displayCtrlLogMsg((char*) "GET_POS: Error");
                }
                else
                {
                    uint8_t* value = &rxBuffer[3];

                    mksMotorEncoder = (int64_t) (
                        ((uint64_t) value[0] << 40) |
                        ((uint64_t) value[1] << 32) |
                        ((uint64_t) value[2] << 24) |
                        ((uint64_t) value[3] << 16) |
                        ((uint64_t) value[4] << 8) |
                        ((uint64_t) value[5] << 0)
                        );

                    mksMotorCmdQueue[0].status = MKS_MOTOR_STATUS_IDLE;
                }

                break;

            case CTRL_CMD_POSITION_SET:
                LOG_MSGLN("mksLoop: SET_POSITION");
                displayCtrlMsgTemp((char*) "SET_POSITION", 5);
                displayCtrlLogMsg((char*) "SET_POS");

                mksMotorCmdQueue[0].status = MKS_MOTOR_STATUS_EXEC;

                // Sanity check
                if((mksMotorCmdQueue[0].parami_01 < mksMotorMax) && (mksMotorCmdQueue[0].parami_01 > mksMotorMin))
                {
                    ackStatus = setMksMotorPosition3(mksMotorSlaveAddr, mksMotorSpeed, mksMotorAccel, mksMotorCmdQueue[0].parami_01);
                    if( ackStatus == 2 )
                    {
                        mksMotorCmdQueue[0].status = MKS_MOTOR_STATUS_IDLE;
                        displayCtrlLogMsg((char*) "SET_POS: Ok");
                    }
                    else
                    {
                        mksMotorCmdQueue[0].status = MKS_MOTOR_STATUS_ERROR;
                        displayCtrlLogMsg((char*) "SET_POS: Error");
                    }
                }
                else
                {
                    // skip command
                    mksMotorCmdQueue[0].status = MKS_MOTOR_STATUS_IDLE;
                    displayCtrlLogMsg((char*) "SET_POS: Skipped");
                }

                break;

            case CTRL_CMD_SPEED_GET:
                LOG_MSGLN("mksLoop: GET_SPEED, not supported yet");
                displayCtrlLogMsg((char*) "CMD_SPEED_GET, skip");
                mksMotorCmdQueue[0].status = MKS_MOTOR_STATUS_IDLE;
                break;

            case CTRL_CMD_ACCEL_SET:
                LOG_MSGLN("mksLoop: SET_ACCEL, not supported yet");
                displayCtrlLogMsg((char*) "CMD_ACCEL_SET, skip");
                mksMotorCmdQueue[0].status = MKS_MOTOR_STATUS_IDLE;
                break;

            case CTRL_CMD_ACCEL_GET:
                LOG_MSGLN("mksLoop: GET_ACCEL, not supported yet");
                displayCtrlLogMsg((char*) "CMD_ACCEL_GET, skip");
                mksMotorCmdQueue[0].status = MKS_MOTOR_STATUS_IDLE;
                break;

            case CTRL_CMD_SPEED_SET:
                LOG_MSGLN("mksLoop: SET_SPEED, not supported yet");
                displayCtrlLogMsg((char*) "CMD_SPEED_SET, skip");
                mksMotorCmdQueue[0].status = MKS_MOTOR_STATUS_IDLE;
                break;

            case CTRL_CMD_MKS_RESET:
                LOG_MSGLN("mksLoop: MKS_RESET, not supported yet");
                displayCtrlLogMsg((char*) "CMD_MKS_RESET, skip");
                /* add here other motor control operations, like stop */
                mksMotorCmdQueue[0].status = MKS_MOTOR_STATUS_IDLE;
                break;

            case CTRL_CMD_STATUS_GET:
                LOG_MSGLN("mksLoop: CTRL_CMD_STATUS_GET, not supported yet");
                displayCtrlLogMsg((char*) "CMD_STATUS_GET, skip");
                mksMotorCmdQueue[0].status = MKS_MOTOR_STATUS_IDLE;
                break;

            case CTRL_CMD_ZERO_SET:
                LOG_MSGLN("mksLoop: CTRL_CMD_ZERO_SET");
                displayCtrlLogMsg((char*) "CMD_ZERO_SET");

                mksMotorCmdQueue[0].status = MKS_MOTOR_STATUS_EXEC;
                ackStatus = mksSetAxisZero(mksMotorSlaveAddr);
                if( ackStatus == 1 )
                {
                    mksMotorCmdQueue[0].status = MKS_MOTOR_STATUS_IDLE;
                    displayCtrlLogMsg((char*) "CMD_ZERO_SET, Ok");

                }
                else
                {
                    mksMotorCmdQueue[0].status = MKS_MOTOR_STATUS_ERROR;
                    displayCtrlLogMsg((char*) "CMD_ZERO_SET, Error");

                }
                break;

            case CTRL_CMD_GO_ZERO:
                LOG_MSGLN("mksLoop: CTRL_CMD_GO_ZERO, not supported yet");
                displayCtrlLogMsg((char*) "CMD_GO_ZERO, skip");
                mksMotorCmdQueue[0].status = MKS_MOTOR_STATUS_IDLE;
                break;

            default:
                LOG_MSGLN("mksLoop: unknown MKS command, skipped");
                displayCtrlLogMsg((char*) "CMD Unknown, skip");
                mksMotorCmdQueue[0].status = MKS_MOTOR_STATUS_IDLE;
        }

    }
}

int8_t mksCmdRequest(int8_t command, int32_t parami_01, int32_t parami_02, float paramf_01, float paramf_02)
{
    if( mksMotorCmdQueue[0].status > 0 )
    {
        return 1;
    }

    if( mksMotorCmdQueue[0].status < 0 )
    {
        return -1;
    }

    /* insert parameter in Queue */
    mksMotorCmdQueue[0].command = command;
    mksMotorCmdQueue[0].parami_01 = parami_01;
    mksMotorCmdQueue[0].parami_02 = parami_02;
    mksMotorCmdQueue[0].paramf_01 = paramf_01;
    mksMotorCmdQueue[0].paramf_01 = paramf_02;

    /* signal status */
    mksMotorCmdQueue[0].status = MKS_MOTOR_STATUS_BUSY;

    return 0;
}

/*
   Function: Calculate the checksum of a set of data
   Input: buffer data to be verified
        size The number of data to be verified
   output: checksum
 */
uint8_t mksGetCheckSum(uint8_t* buffer, uint8_t size)
{
    uint8_t i;
    uint16_t sum = 0;
    for( i = 0; i < size; i++ )
    {
        sum += buffer[i]; // Calculate accumulated value
    }
    return(sum & 0xFF); // return checksum
}

/*
   Function: Wait for the response from the lower computer, set the timeout time to 3000ms
   enter:
   delayTime waiting time (ms),
   delayTime = 0 , wait indefinitely
   output:
   Position mode 2 control start 1
   Position mode 2 control completed 2
   Position mode 2 control failure 0
   timeout no reply 0
 */
uint8_t mksWaitingForACK(uint32_t len, uint32_t delayTime, uint8_t retValIdx, bool retValOverride)
{
    uint8_t retVal; // return value
    unsigned long sTime; // timing start time
    unsigned long time; // current moment
    uint8_t rxByte;

    if(retValIdx >= MKS_BUFFER_SIZE)
    {
        return 0;
    }

    sTime = millis(); // get the current moment
    rxCnt = 0; // Receive count value set to 0
    while( 1 )
    {
        if( Serial1.available() > 0 ) // The serial port receives data
        {
            rxByte = Serial1.read(); // read 1 byte data
            if( rxCnt != 0 )
            {
                rxBuffer[rxCnt++] = rxByte; // Storing data
            }
            else if( rxByte == 0xFB ) // Determine whether the frame header
            {
                rxBuffer[rxCnt++] = rxByte; // store frame header
            }
        }

        if( rxCnt == len ) // Receive complete
        {
            if( rxBuffer[len - 1] == mksGetCheckSum(rxBuffer, len - 1))
            {
                retVal = rxBuffer[retValIdx]; // checksum correct

                if(retValOverride)
                {
                    retVal=1;
                }

                break; // exit while(1)
            }
            else
            {
                rxCnt = 0; // Verification error, re-receive the response
            }
        }

        time = millis();
        if((delayTime != 0) && ((time - sTime) > delayTime)) // Judging whether to time out
        {
            retVal = 0;
            break; // timeout, exit while(1)
        }

        delay(BSP_DELAY_3MS);
    }
    return(retVal);
}

int8_t getMksMotorStatus(uint8_t slaveAddr)
{
    int8_t rv = -1;

    int i;
    uint16_t checkSum = 0;
    uint8_t ackStatus;

    /* manual 6.2.1: query motor */
    txBuffer[0] = 0xFA; // frame header
    txBuffer[1] = slaveAddr; // slave address
    txBuffer[2] = 0xF1; // function code
    txBuffer[3] = mksGetCheckSum(txBuffer, 3); // Calculate checksum

    // Send command
    Serial1.write(txBuffer, 4);

    // Wait to start answering
    ackStatus = mksWaitingForACK(5, 3000, 3,false);
    if( ackStatus > 0 )
    {
        // Response completed
        rv = rxBuffer[3];
        if( rv == 0 )
        {
            rv = -1; // failure
        }
    }
    else
    {
        // Incomplete response
        ledRgbBlinkN(ledRgbColorRed, 0.5 * ONESEC_MSECS, 3);
    }

    return rv;
}

int8_t setMksMotorPosition3(uint8_t slaveAddr, uint16_t speed, uint8_t acc, int32_t absAxis)
{
    int i;
    uint16_t checkSum = 0;
    uint8_t ackStatus;

    txBuffer[0] = 0xFA; // frame header
    txBuffer[1] = slaveAddr; // slave address
    txBuffer[2] = 0xF5; // function code
    txBuffer[3] = (speed >> 8) & 0x00FF; // 8 bit higher speed
    txBuffer[4] = speed & 0x00FF; // 8 bits lower
    txBuffer[5] = acc; // acceleration
    txBuffer[6] = (absAxis >> 24) & 0xFF; // Absolute coordinates bit31 - bit24
    txBuffer[7] = (absAxis >> 16) & 0xFF; // Absolute coordinates bit23 - bit16
    txBuffer[8] = (absAxis >> 8) & 0xFF; // Absolute coordinates bit15 - bit8
    txBuffer[9] = (absAxis >> 0) & 0xFF; // Absolute coordinates bit7 - bit0
    txBuffer[10] = mksGetCheckSum(txBuffer, 10); // Calculate checksum

    Serial1.write(txBuffer, 11);

    // Wait for the position control to start answering
    ackStatus = mksWaitingForACK(5, 3000, 3, false);

    if( ackStatus == 1 )
    {
        // Position control starts

        // Wait for the position control to complete the response
        ackStatus = mksWaitingForACK(5, 0, 3, false);
        if( ackStatus == 2 )
        {
            // Receipt of position control complete response

            /* nothing to do */
        }
        else
        {
            // Location complete reply not received
            ledRgbBlinkN(ledRgbColorRed, 0.5 * ONESEC_MSECS, 3);
        }
    }
    else
    {
        // Position control failed
        ledRgbBlinkN(ledRgbColorViolet, 0.5 * ONESEC_MSECS, 3);
    }

    return ackStatus;
}

/*
   Function: Serial port sends position mode 3 running command
   Input: slaveAddr slave address
       speed running speed
       acc acceleration
       absAxis absolute coordinates
 */
void mksPositionMode3Run(uint8_t slaveAddr, uint16_t speed, uint8_t acc, int32_t absAxis)
{
    int i;
    uint16_t checkSum = 0;

    txBuffer[0] = 0xFA; // frame header
    txBuffer[1] = slaveAddr; // slave address
    txBuffer[2] = 0xF5; // function code
    txBuffer[3] = (speed >> 8) & 0x00FF; // 8 bit higher speed
    txBuffer[4] = speed & 0x00FF; // 8 bits lower
    txBuffer[5] = acc; // acceleration
    txBuffer[6] = (absAxis >> 24) & 0xFF; // Absolute coordinates bit31 - bit24
    txBuffer[7] = (absAxis >> 16) & 0xFF; // Absolute coordinates bit23 - bit16
    txBuffer[8] = (absAxis >> 8) & 0xFF; // Absolute coordinates bit15 - bit8
    txBuffer[9] = (absAxis >> 0) & 0xFF; // Absolute coordinates bit7 - bit0
    txBuffer[10] = mksGetCheckSum(txBuffer, 10); // Calculate checksum

    Serial1.write(txBuffer, 11);

}

int8_t mksSetAxisZero(uint8_t slaveAddr)
{
    int i = 0;
    uint16_t checkSum = 0;
    uint8_t ackStatus;

    txBuffer[i++] = 0xFA;
    txBuffer[i++] = slaveAddr;
    txBuffer[i++] = 0x92;
    txBuffer[i] = mksGetCheckSum(txBuffer, i);

    Serial1.write(txBuffer, (i + 1));

    ackStatus = mksWaitingForACK(5, 3000, 3, false);

    return ackStatus;
}

int8_t getMksEncoderValue(uint8_t slaveAddr)
{
    int i = 0;
    uint16_t checkSum = 0;
    uint8_t ackStatus;

    txBuffer[i++] = 0xFA;
    txBuffer[i++] = slaveAddr;
    txBuffer[i++] = 0x31;
    txBuffer[i] = mksGetCheckSum(txBuffer, i);
    Serial1.write(txBuffer, (i + 1));

    // Wait for the position control to start answering
    ackStatus = mksWaitingForACK(10, 3000, 0, true);

    return ackStatus;
}