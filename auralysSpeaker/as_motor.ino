/* ============================================================================= */
/* MKS MOTOR CONTROL                                                             */
/* ============================================================================= */

void mksSetup()
{
    Serial1.begin(UART_MKS_BAUD, SERIAL_8N1, UART_MKS_RX_PIN, UART_MKS_TX_PIN);
}

void mksLoop()
{

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
    for(i = 0; i < size; i++)
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
uint8_t mksWaitingForACK(uint32_t len, uint32_t delayTime)
{
    uint8_t retVal; // return value
    unsigned long sTime; // timing start time
    unsigned long time; // current moment
    uint8_t rxByte;

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
                retVal = rxBuffer[3]; // checksum correct
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
    ackStatus = mksWaitingForACK(5, 3000);
    if( ackStatus > 0 )
    {

        // Response completed
        rv = rxBuffer[3];
        if( rv == 0 )
        {
            rv = -1;   // failure
        }
    }
    else
    {
        // Incomplete response
        ledRgbBlinkN(ledRgbColorRed, 0.5 * ONESEC_MSECS, 3);
    }

    return rv;
}

uint64_t getMksEncoderValueCarry(uint8_t slaveAddr)
{
    // int i;
    // uint16_t checkSum = 0;

    // txBuffer[0] = 0xFA; // frame header
    // txBuffer[1] = slaveAddr; // slave address
    // txBuffer[2] = 0xF5; // function code
    // txBuffer[3] = (speed >> 8) & 0x00FF; // 8 bit higher speed
    // txBuffer[4] = speed & 0x00FF; // 8 bits lower
    // txBuffer[5] = acc; // acceleration
    // txBuffer[6] = (absAxis >> 24) & 0xFF; // Absolute coordinates bit31 - bit24
    // txBuffer[7] = (absAxis >> 16) & 0xFF; // Absolute coordinates bit23 - bit16
    // txBuffer[8] = (absAxis >> 8) & 0xFF; // Absolute coordinates bit15 - bit8
    // txBuffer[9] = (absAxis >> 0) & 0xFF; // Absolute coordinates bit7 - bit0
    // txBuffer[10] = mksGetCheckSum(txBuffer, 10); // Calculate checksum

    // Serial1.write(txBuffer, 11);

    return 0;

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
    ackStatus = mksWaitingForACK(5, 3000);

    if( ackStatus == 1 )
    {
        // Position control starts

        // Wait for the position control to complete the response
        ackStatus = mksWaitingForACK(5, 0);
        if( ackStatus == 2 )
        {
            // Receipt of position control complete response
            // if( absoluteAxis == 0 )
            // {
            // absoluteAxis = AXIS_INIT; // 81920;//163840;    //Set absolute coordinates
            // }
            // else
            // {
            // absoluteAxis = 0;
            // }

            absoluteAxis = -1 * absoluteAxis;

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
