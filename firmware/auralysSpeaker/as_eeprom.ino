/* ============================================================================= */
/* EEPROM                                                                        */
/* ============================================================================= */


/*
 *  ============================== ESP32 INTERNAL EEPROM =======================
 */

inline void eepromReadBytes(byte* dst, uint16_t src, uint16_t src_size)
{
    uint16_t i = 0;
    if((NULL != dst) && (src_size > 0) && ((src + src_size) < 1024))
    {
        for( i = 0; i < src_size; i++ )
        {
            *(dst + i) = EEPROM.read(src + i);
        }
        delay(10);
    }
}

inline void eepromWriteBytes(uint16_t dst, byte* src, uint16_t src_size)
{
    uint16_t i = 0;
    if((NULL != src) && (src_size > 0) && ((dst + src_size) < 1024))
    {
        for( i = 0; i < src_size; i++ )
        {
            EEPROM.write(dst + i, (byte) * (src + i));
        }
        delay(10);
    }
}

void eepromUpdateBytes(uint16_t dst, byte* src, uint16_t src_size)
{
    uint16_t i = 0;
    byte tmp_byte = 0;
    if((NULL != src) && (src_size > 0) && ((dst + src_size) < 1024))
    {
        for( i = 0; i < src_size; i++ )
        {
            tmp_byte = EEPROM.read(dst + i);
            if( tmp_byte != ((byte) * (src + i)))
            {
                EEPROM.write(dst + i, (byte) * (src + i));
            }
        }
        delay(10);
    }
}

void eepromUpdateByte(uint16_t dst, byte src)
{
    uint16_t i = 0;
    byte tmp_byte = 0;

    tmp_byte = EEPROM.read(dst);

    if( tmp_byte != src )
    {
        EEPROM.write(dst, src);
    }
    // EEPROM.commit();
}

void eepromCommit()
{
    /* ESP simulates EEPROM using FLASH, avoid wearing out flash on debug*/
    EEPROM.commit();
}

void eepromSetup()
{
    uint8_t tmp8 = 0;

    EEPROM.begin(EE_SIZE_BYTES);

    /* ToDo: read the eeprom and make sure the signature */
    /* is present to mark a valid system image           */

    /* ToDo: read the eeprom data section and            */
    /* find the slot with the latest datetime            */
    /* so that we do not rollover in a wrong manner      */
    /* NOTE: for now we always start from ZERO           */
    // efslog_idx = 0;

    /* this flag will tell us if the hardware            */
    /* has been installed and initialized once           */
    eepromReadBytes(&tmp8, EE_SYS_INIT_FLAG_OFFS, EE_SYS_INIT_FLAG_SIZE);

    /* BIT 00 : bsp_initialization_flag */
    bspInitialized = tmp8 & EE_SYS_INIT_BSPINITIALIZED_MSK;
    LOG_MSG("[EEPROM] eeprom setup, bspInitialized:");
    LOG_MSGLN((bspInitialized) ? "YES" : "NO");

    /* BIT 01 : bsp_activation_flag */
    bspActivated = (tmp8 & EE_SYS_INIT_BSPACTIVATED_MSK) >> 1;
    LOG_MSG("[EEPROM] eeprom setup, bspActivated:");
    LOG_MSGLN((bspActivated) ? "YES" : "NO");

    if( bspInitialized )
    {
        /* hostname from hw */
        for( uint8_t i = 0; i < 9; i++ )
        {
            device_hostname[15 - i] = hw_config.hw_pcb_uuid4[31 - i];
        }

        eepromGetConfigs();
    }
}

void eepromGetConfigs()
{
    /* read hw section */
    eepromReadBytes(&hw_config.hw_unit_type, EE_HW_UNIT_TYPE_OFFS, EE_HW_UNIT_TYPE_SIZE);
    eepromReadBytes(&hw_config.hw_mks_speed, EE_HW_MKS_SPEED_OFFS, EE_HW_MKS_SPEED_SIZE);
    eepromReadBytes(&hw_config.hw_mks_accel, EE_HW_MKS_ACCEL_OFFS, EE_HW_MKS_ACCEL_SIZE);
}

void eepromSetConfigs()
{
    /* empty */
}

void eepromLoop()
{
    /* nothing to do */
}
