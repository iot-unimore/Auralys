/* ============================================================================= */
/* EEPROM                                                                        */
/* ============================================================================= */


/*
 *  ============================== ST25DV EEPROM (log data) =======================
 */

// void nfcReadNfcTagENDA(uint16_t* val_list)
// {
// uint8_t tmp = 0;

// if( !nfctag_enabled )
// {
// return;
// }

// for(tmp = 0; tmp < 3; tmp++)
// {
// *(val_list + tmp) = nfctag.getENDA(tmp + 1);
// }

///* sanity check */
// if(((*(val_list + 0)) < 7) || ((*(val_list + 1)) < 15) || ((*(val_list + 0)) >= (*(val_list + 1))))
// {
// LOG_MSGLN("[BSP] Error: nfctag not partitioned.");
// nfctag_enabled = false;
// }
// }

// void nfcReadPcbConfig(HW_PCB_CONFIG_T* cfg)
// {
// uint16_t offs = 0;
// uint8_t i = 0;
// uint8_t tmp8;
// char wmark[9] = { '\0' };

// if( !nfctag_enabled )
// {
// return;
// }

// if( NULL == cfg )
// {
// return;
// }

///* ************************** */
///* wmark */
///* ************************** */
// for(i = 0; i < NFCTAG_WMARK_SIZE - 2; i++)
// {
// wmark[i] = nfctag.readByte(offs + i);
// if( wmark[i] != NFCTAG_WMARK[i] )
// {
// LOG_MSGLN("[nfcReadPcbConfig] Invalid WMARK!");
// nfctag_enabled = false;
// return;
// }
// }
///* last two bytes */
// wmark[i] = nfctag.readByte(offs + i);
// i++;
// wmark[i] = nfctag.readByte(offs + i);
// i++;
// wmark[NFCTAG_WMARK_SIZE] = '\0';
// offs += NFCTAG_WMARK_SIZE;

// LOG_MSGLN("[nfcReadPcbConfig] WMARK is OK!");

///* ************************** */
///* HW DESCRIPTOR */
///* ************************** */
// cfg->hw_section_size = nfctag.readByte(offs);
// offs++;

///* hw_descriptor_mjr */
// cfg->hw_descriptor_mjr = nfctag.readByte(offs);
// offs++;

///* hw_descriptor_min */
// cfg->hw_descriptor_min = nfctag.readByte(offs);
// offs++;

///* owner firstname */
// for(i = 0; i < HW_ID_SIZE; i++)
// {
// cfg->hw_owner_firstname[i] = nfctag.readByte(offs + i);
// }
// cfg->hw_owner_firstname[HW_ID_SIZE] = '\0';
// offs += HW_ID_SIZE;

///* owner lastname */
// for(i = 0; i < HW_ID_SIZE; i++)
// {
// cfg->hw_owner_lastname[i] = nfctag.readByte(offs + i);
// }
// cfg->hw_owner_lastname[HW_ID_SIZE] = '\0';
// offs += HW_ID_SIZE;

///* owner phone number */
// for(i = 0; i < HW_PHONENUM_SIZE; i++)
// {
// cfg->hw_owner_phonenum[i] = nfctag.readByte(offs + i);
// }
// cfg->hw_owner_phonenum[HW_PHONENUM_SIZE] = '\0';
// offs += HW_PHONENUM_SIZE;

///* operator ID */
// for(i = 0; i < HW_ID_SIZE; i++)
// {
// cfg->hw_operator_id[i] = nfctag.readByte(offs + i);
// }
// cfg->hw_operator_id[HW_ID_SIZE] = '\0';
// offs += HW_ID_SIZE;

///* operator phone number */
// for(i = 0; i < HW_PHONENUM_SIZE; i++)
// {
// cfg->hw_operator_phonenum[i] = nfctag.readByte(offs + i);
// }
// cfg->hw_operator_phonenum[HW_PHONENUM_SIZE] = '\0';
// offs += HW_PHONENUM_SIZE;

// for(i = 0; i < HW_CODENAME_SIZE; i++)
// {
// cfg->hw_codename[i] = nfctag.readByte(offs + i);
// }
// cfg->hw_codename[HW_CODENAME_SIZE] = '\0';
// offs += HW_CODENAME_SIZE;

// for(i = 0; i < HW_CPU_ARCH_SIZE; i++)
// {
// cfg->hw_cpu_arch[i] = nfctag.readByte(offs + i);
// }
// cfg->hw_cpu_arch[HW_CPU_ARCH_SIZE] = '\0';
// offs += HW_CPU_ARCH_SIZE;

// for(i = 0; i < HW_CPU_TYPE_SIZE; i++)
// {
// cfg->hw_cpu_type[i] = nfctag.readByte(offs + i);
// }
// cfg->hw_cpu_type[HW_CPU_TYPE_SIZE] = '\0';
// offs += HW_CPU_TYPE_SIZE;

// cfg->hw_pcb_ver_mjr = nfctag.readByte(offs);
// offs++;

// cfg->hw_pcb_ver_min = nfctag.readByte(offs);
// offs++;

///* UUID */
// for(i = 0; i < 32; i++)
// {
// cfg->hw_pcb_uuid4[i] = nfctag.readByte(offs + i);
// }
// cfg->hw_pcb_uuid4[32] = '\0';
// offs += 32;

// tmp8 = nfctag.readByte(offs);
// offs++;
// cfg->hw_pcb_batbkp_v_max = (tmp8 >> 4) + 1;
// cfg->hw_pcb_batbkp_v_min = tmp8 & 0x0F;

// tmp8 = nfctag.readByte(offs);
// offs++;
// cfg->hw_pcb_bat_v_max = (tmp8 >> 4) + 1;
// cfg->hw_pcb_bat_v_min = tmp8 & 0x0F;

// tmp8 = nfctag.readByte(offs);
// offs++;
// cfg->hw_pcb_pwr_v_max = (tmp8 >> 4) + 1;
// cfg->hw_pcb_pwr_v_min = tmp8 & 0x0F;

// tmp8 = nfctag.readByte(offs);
// offs++;
// cfg->hw_pcb_sol_v_max = (tmp8 >> 4) + 1;
// cfg->hw_pcb_sol_v_min = tmp8 & 0x0F;

// cfg->hw_pcb_build_data_year_from_epoch = nfctag.readByte(offs);
// offs++;

// cfg->hw_pcb_build_data_month = nfctag.readByte(offs);
// offs++;

// cfg->hw_pcb_build_data_day = nfctag.readByte(offs);
// offs++;

///* sensor config */
// tmp8 = nfctag.readByte(offs);
// offs++;
// cfg->hw_sensor_type_thermal_num = tmp8 & 0xF;
// cfg->hw_sensor_type_thermal = tmp8 >> 4;

// tmp8 = nfctag.readByte(offs);
// offs++;
// cfg->hw_sensor_type_pressure_num = tmp8 & 0xF;
// cfg->hw_sensor_type_pressure = tmp8 >> 4;

// tmp8 = nfctag.readByte(offs);
// offs++;
// cfg->hw_sensor_type_humidity_num = tmp8 & 0xF;
// cfg->hw_sensor_type_humidity = tmp8 >> 4;

// tmp8 = nfctag.readByte(offs);
// offs++;
// cfg->hw_sensor_type_light_num = tmp8 & 0xF;
// cfg->hw_sensor_type_light = tmp8 >> 4;

// tmp8 = nfctag.readByte(offs);
// offs++;
// cfg->hw_sensor_type_motion_num = tmp8 & 0xF;
// cfg->hw_sensor_type_motion = tmp8 >> 4;

// tmp8 = nfctag.readByte(offs);
// offs++;
// cfg->hw_pcb_type_bat = tmp8 >> 4;
// cfg->hw_ext_temperature_alarm = (tmp8 & 0x03) << 8;

///* hw_ext_temperature_alarm (lower 8 bits) */
// tmp8 = nfctag.readByte(offs);
// offs++;
// cfg->hw_ext_temperature_alarm |= tmp8;

///* led config was introduced in hw_config version 0.3 */
// if((float) (cfg->hw_descriptor_mjr * 1.0 + cfg->hw_descriptor_min * 0.1) >= 0.3 )
// {
// tmp8 = nfctag.readByte(offs);
// offs++;
// cfg->hw_led_type_rgb_num = tmp8 & 0xF;
// cfg->hw_led_type_rgb = tmp8 >> 4;
// }

///* gps/modem config was introduced in hw_config version 0.4 */
// if((float) (cfg->hw_descriptor_mjr * 1.0 + cfg->hw_descriptor_min * 0.1) >= 0.4 )
// {
// tmp8 = nfctag.readByte(offs);
// offs++;
// cfg->hw_modem_type = tmp8 & 0xF;
// cfg->hw_gps_type = tmp8 >> 4;
// }

// LOG_MSG("[nfcReadPcbConfig] hw descriptor size: ");
// LOG_MSGLN(offs);
// LOG_MSG("");

///* SANITY CHECK: last two bytes of wmark must be the year of fabrication */
//// ToDo
// }

// bool nfcUpdatePcbConfig(HW_PCB_CONFIG_T* cfg)
// {
///* this function is used to update ownersip of the device */

// uint16_t offs = 0;
// uint8_t i = 0;

// if( !nfctag_enabled )
// {
// return false;
// }

// if( NULL == cfg )
// {
// return false;
// }

// offs = 0;

///* skip wmark */
// offs += NFCTAG_WMARK_SIZE;
///* skip section size */
// offs += 1;
///* skip hw_descriptor_mjr */
// offs += 1;
///* skip hw_descriptor_min */
// offs += 1;

// if( 1 )
// {
///* owner firstname: clear & set */
// LOG_MSG("[nfcUpdatePcbConfig] firstname: ");
// LOG_MSGLN(cfg->hw_owner_firstname);
// for(i = 0; i < HW_ID_SIZE; i++)
// {
// nfctag.writeByte(offs + i, ' ');
// }
// for(i = 0; i < strlen(cfg->hw_owner_firstname); i++)
// {
// nfctag.writeByte(offs + i, cfg->hw_owner_firstname[i]);
// }
// nfctag.writeByte(offs + i, '\0');
// offs += HW_ID_SIZE;

///* owner lastname: clear & set  */
// LOG_MSG("[nfcUpdatePcbConfig] lastname: ");
// LOG_MSGLN(cfg->hw_owner_lastname);
// for(i = 0; i < HW_ID_SIZE; i++)
// {
// nfctag.writeByte(offs + i, ' ');
// }
// for(i = 0; i < strlen(cfg->hw_owner_lastname); i++)
// {
// nfctag.writeByte(offs + i, cfg->hw_owner_lastname[i]);
// }
// nfctag.writeByte(offs + i, '\0');
// offs += HW_ID_SIZE;

///* owner phonenum: clear & set */
// LOG_MSG("[nfcUpdatePcbConfig] owner phone: ");
// LOG_MSGLN(cfg->hw_owner_phonenum);
// for(i = 0; i < HW_PHONENUM_SIZE; i++)
// {
// nfctag.writeByte(offs + i, ' ');
// }
// for(i = 0; i < strlen(cfg->hw_owner_phonenum); i++)
// {
// nfctag.writeByte(offs + i, cfg->hw_owner_phonenum[i]);
// }
// nfctag.writeByte(offs + i, '\0');
// offs += HW_PHONENUM_SIZE;

///* operator ID: clear & set  */
// LOG_MSG("[nfcUpdatePcbConfig] operator_id: ");
// LOG_MSGLN(cfg->hw_operator_id);
// for(i = 0; i < HW_ID_SIZE; i++)
// {
// nfctag.writeByte(offs + i, ' ');
// }
// for(i = 0; i < strlen(cfg->hw_operator_id); i++)
// {
// nfctag.writeByte(offs + i, cfg->hw_operator_id[i]);
// }
// nfctag.writeByte(offs + i, '\0');
// offs += HW_ID_SIZE;

///* operator phone number: clear & set */
// LOG_MSG("[nfcUpdatePcbConfig] operator phone: ");
// LOG_MSGLN(cfg->hw_operator_phonenum);
// for(i = 0; i < HW_PHONENUM_SIZE; i++)
// {
// nfctag.writeByte(offs + i, ' ');
// }
// for(i = 0; i < strlen(cfg->hw_operator_phonenum); i++)
// {
// nfctag.writeByte(offs + i, cfg->hw_operator_phonenum[i]);
// }
// nfctag.writeByte(offs + i, '\0');
// offs += HW_PHONENUM_SIZE;

// }
// return true;
// }

// void nfcWriteSwConfig(HW_PCB_CONFIG_T* cfg)
// {
// uint16_t offs = 0;
// uint8_t i = 0;
// uint8_t tmp8, tmp_mjr, tmp_min, tmp_rev, tmp_build;
// uint16_t sw_offs;

// if( !nfctag_enabled )
// {
// return;
// }

// if( NULL == cfg )
// {
// return;
// }

// offs = 0;

///* skip watermark field */
// offs += NFCTAG_WMARK_SIZE;

///* read hw pcb description section by reading its size */
// sw_offs = nfctag.readByte(offs);
// LOG_MSG("[nfcWriteSwConfig] sw_offset begin: ");
// LOG_MSGLN(sw_offs);

///* skip hw section */
// offs = sw_offs;

///* skip sw_description_size field */
// offs++;

///* check if we already have same infos */
// tmp_mjr = nfctag.readByte(offs); offs++;
// tmp8 = nfctag.readByte(offs); offs++;
// tmp_min = tmp8 >> 4;
// tmp_rev = (tmp8 >> 2) & 0x03;
// tmp_build = tmp8 & 0x03;

// if((tmp_mjr != SW_VER_MJR) || (tmp_min != SW_VER_MIN) ||
// (tmp_rev != SW_VER_REV) || (tmp_build != SW_VER_BUILD))
// {
///* update sw description section */
// LOG_MSGLN("[nfcWriteSwConfig] Updating NFCTag SW description.")

///* skip hw section */
// offs = sw_offs;

///* skip sw description size */
// offs++;

///* sw.mjr */
// nfctag.writeByte(offs, SW_VER_MJR);
// offs++;
///* sw.min|rev|build */
// nfctag.writeByte(offs, ((SW_VER_MIN & 0x0F) << 4) | ((SW_VER_REV & 0x03) << 2) | (SW_VER_BUILD & 0x03));
// offs++;

///* platform */
// for(i = 0; i < strlen(BRWS_SW_PLATFORM); i++)
// {
// nfctag.writeByte(offs + i, BRWS_SW_PLATFORM[i]);
// }
// for(i = strlen(BRWS_SW_PLATFORM); i < BRWS_SW_PLATFORM_SIZE_MAX; i++)
// {
// nfctag.writeByte(offs + i, '\0');
// }
// offs += BRWS_SW_PLATFORM_SIZE_MAX;

///* codename */
// for(i = 0; i < strlen(BRWS_SW_CODENAME); i++)
// {
// nfctag.writeByte(offs + i, BRWS_SW_CODENAME[i]);
// }
// for(i = strlen(BRWS_SW_CODENAME); i < BRWS_SW_CODENAME_SIZE_MAX; i++)
// {
// nfctag.writeByte(offs + i, '\0');
// }
// offs += BRWS_SW_CODENAME_SIZE_MAX;

// LOG_MSG("[nfcWriteSwConfig] sw_offset end: ");
// LOG_MSGLN(sw_offs);

///* rewrite section size */
// nfctag.writeByte(sw_offs, (offs - sw_offs));

// LOG_MSG("[nfcWriteSwConfig] sw_descriptor size: ");
// LOG_MSGLN((offs - sw_offs));

// }
// else
// {
// LOG_MSGLN("[BSP] SW description ALREADY updated.")
// }

// }

// void nfcWriteLog(uint16_t lineIdx, EFSLOG_ENTRY_T* lineLog)
// {
// int i = 0;
// int tmpOff = 0;
// int areaSize = 0;

// if( !nfctag_enabled )
// {
// return;
// }

///* DataLog is on Area 2 (Area-1 is for config data) */
// tmpOff = (nfctag_ENDA[0] + 1) * 32 + lineIdx * EE_SECTION_EFSLOG_ITEM_SIZE;

///* safety wrap */
// areaSize = (nfctag_ENDA[1] - nfctag_ENDA[0] + 1) * 32;
// lineIdx = lineIdx % areaSize;


///* IMPORTANT: write syntax in big endian as per EFESTO PAYLOAD SYNTAX specs */
// nfctag.writeByte(tmpOff, ((lineLog->ver_mjr << 4) | (lineLog->ver_min & 0xF))); tmpOff++;
// nfctag.writeByte(tmpOff, (lineLog->flag_1 << 7) | (lineLog->rssi_lkg & 0x7F)); tmpOff++; // byte: FLAG_1 | dr
// nfctag.writeByte(tmpOff, lineLog->year); tmpOff++;
// nfctag.writeByte(tmpOff, (lineLog->flag_2 << 7) | ((lineLog->snr & 0x1F) << 2) | (lineLog->month >> 2)); tmpOff++; // byte: FLAG_2 | snr | MONTH.HIGH
// nfctag.writeByte(tmpOff, ((lineLog->month & 0x03) << 6) | (lineLog->day << 1) | (lineLog->hour >> 4)); tmpOff++;
// nfctag.writeByte(tmpOff, ((lineLog->hour & 0x0F) << 4) | (lineLog->minute >> 2)); tmpOff++;
// nfctag.writeByte(tmpOff, ((lineLog->minute & 0x03) << 6) | lineLog->second); tmpOff++;
// nfctag.writeByte(tmpOff, lineLog->sysflags); tmpOff++;
// nfctag.writeByte(tmpOff, lineLog->temp_int); tmpOff++;
// nfctag.writeByte(tmpOff, lineLog->humidity); tmpOff++;
// nfctag.writeByte(tmpOff, lineLog->pressure); tmpOff++;
///* temperatures are in 12bits, pack them && take care of leftovers */
// nfctag.writeByte(tmpOff, lineLog->temp_ext_01 >> 4); tmpOff++;
// nfctag.writeByte(tmpOff, ((lineLog->temp_ext_01 & 0x0F) << 4) | (lineLog->dr_lkg)); tmpOff++;
///* voltages are 8bit */
// nfctag.writeByte(tmpOff, lineLog->v_bat); tmpOff++;
// nfctag.writeByte(tmpOff, lineLog->v_in); tmpOff++;
///* reserved byte */
// nfctag.writeByte(tmpOff, 0); tmpOff++;
// }

// void nfcPrintPcbConfig(HW_PCB_CONFIG_T* cfg)
// {
// #ifdef DEBUG
// uint8_t tmp;

// Serial.println("\nNFCTAG: PCB Config:");
// Serial.println("-------------------");
// Serial.print("hw_section_size: ");
// Serial.println(cfg->hw_section_size);
// Serial.print("Owner Firstname: ");
// Serial.println(cfg->hw_owner_firstname);
// Serial.print("Owner Lastname: ");
// Serial.println(cfg->hw_owner_lastname);
// Serial.print("Operator ID: ");
// Serial.println(cfg->hw_operator_id);
// Serial.print("Codename: ");
// Serial.println(cfg->hw_codename);
// Serial.print("CPU Arch: ");
// Serial.println(cfg->hw_cpu_arch);
// Serial.print("CPU Type: ");
// Serial.println(cfg->hw_cpu_type);
// Serial.print("PCB VER MJR: ");
// Serial.println(cfg->hw_pcb_ver_mjr);
// Serial.print("PCB VER MIN: ");
// Serial.println(cfg->hw_pcb_ver_min);

// Serial.print("UUIDv4: ");
// for(tmp = 0; tmp < 8; tmp++)
// {
// Serial.print(cfg->hw_pcb_uuid4[tmp]);
// }
// Serial.print("-");
// for(tmp = 8; tmp < 12; tmp++)
// {
// Serial.print(cfg->hw_pcb_uuid4[tmp]);
// }
// Serial.print("-");
// for(tmp = 12; tmp < 16; tmp++)
// {
// Serial.print(cfg->hw_pcb_uuid4[tmp]);
// }
// Serial.print("-");
// for(tmp = 16; tmp < 20; tmp++)
// {
// Serial.print(cfg->hw_pcb_uuid4[tmp]);
// }
// Serial.print("-");
// for(tmp = 20; tmp < 32; tmp++)
// {
// Serial.print(cfg->hw_pcb_uuid4[tmp]);
// }
//// Serial.println(cfg.hw_pcb_uuid4);
// Serial.println("");

// Serial.print("BattBkp Vmax (volt): ");
// Serial.println(cfg->hw_pcb_batbkp_v_max);
// Serial.print("BattBkp Vmin (volt): ");
// Serial.println(cfg->hw_pcb_batbkp_v_min);
// Serial.print("Batt Vmax (volt): ");
// Serial.println(cfg->hw_pcb_bat_v_max);
// Serial.print("Batt Vin (volt): ");
// Serial.println(cfg->hw_pcb_bat_v_min);
// Serial.print("PWR Vmax (volt): ");
// Serial.println(cfg->hw_pcb_pwr_v_max);
// Serial.print("PWR Vmin (volt): ");
// Serial.println(cfg->hw_pcb_pwr_v_min);
// Serial.print("SOL Vmax (volt): ");
// Serial.println(cfg->hw_pcb_sol_v_max);
// Serial.print("SOL Vmin (volt): ");
// Serial.println(cfg->hw_pcb_sol_v_min);
// Serial.print("Build Date (YYYY-MM-DD): ");
// Serial.print(cfg->hw_pcb_build_data_year_from_epoch + 1970);
// Serial.print("-");
// Serial.print(cfg->hw_pcb_build_data_month);
// Serial.print("-");
// Serial.println(cfg->hw_pcb_build_data_day);
// Serial.print("Sensor Thermal Type: ");
// Serial.print(cfg->hw_sensor_type_thermal); Serial.print("-");
// Serial.println(cfg->hw_sensor_type_thermal_num);
// Serial.print("Pressure Thermal Type: ");
// Serial.print(cfg->hw_sensor_type_pressure); Serial.print("-");
// Serial.println(cfg->hw_sensor_type_pressure_num);
// Serial.print("Sensor Humidity Type: ");
// Serial.print(cfg->hw_sensor_type_humidity); Serial.print("-");
// Serial.println(cfg->hw_sensor_type_humidity_num);
// Serial.print("Sensor Light Type: ");
// Serial.print(cfg->hw_sensor_type_light); Serial.print("-");
// Serial.println(cfg->hw_sensor_type_light_num);
// Serial.print("Sensor Motion Type: ");
// Serial.print(cfg->hw_sensor_type_motion); Serial.print("-");
// Serial.println(cfg->hw_sensor_type_motion_num);
// Serial.print("Recharge Battery Type: ");
// Serial.println(cfg->hw_pcb_type_bat);
// Serial.print("User Temperature Alarm: ");
// Serial.println(cfg->hw_ext_temperature_alarm);
// Serial.print("RGB Led Type: ");
// Serial.print(cfg->hw_led_type_rgb); Serial.print("-");
// Serial.println(cfg->hw_led_type_rgb_num);
// Serial.print("Modem Type: ");
// Serial.println(cfg->hw_modem_type);
// Serial.print("GPS Type: ");
// Serial.println(cfg->hw_gps_type);
// Serial.println("\n");
// #endif
// }

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
    LOG_MSG("[EEPROM] eeprom init, bspInitialized:");
    LOG_MSGLN((bspInitialized) ? "YES" : "NO");

    /* BIT 01 : bsp_activation_flag */
    bspActivated = (tmp8 & EE_SYS_INIT_BSPACTIVATED_MSK) >> 1;
    LOG_MSG("[EEPROM] eeprom init, bspActivated:");
    LOG_MSGLN((bspActivated) ? "YES" : "NO");

    if( bspInitialized )
    {
        /* hostname from hw */
        for(uint8_t i = 0; i < 9; i++)
        {
            device_hostname[15 - i] = hw_config.hw_pcb_uuid4[31 - i];
        }
    }
}

void eepromGetDefaults()
{
    /* empty */
}

void eepromSetDefaults()
{
    /* empty */
}

void eepromLoop()
{
    /* nothing to do */
}
