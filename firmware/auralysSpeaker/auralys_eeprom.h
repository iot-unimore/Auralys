
#ifndef _H_AURALYS_EEPROM_H_
#define _H_AURALYS_EEPROM_H_

/* ============================================================================= */
/* EEPROM GLOBALS&DEFINES SECTION                                                */
/* ============================================================================= */
#define EE_SIZE_BYTES (256)

#define EE_BRWS_SIGNATURE                                                               "brw"

/* section pointers */
#define EE_SECTION_SYSTEM_ADDR                                                         (0x00)
#define EE_SECTION_SYSTEM_SIZE                                                           (32)
//#define EE_SECTION_EFSLOG_ADDR              (EE_SECTION_SYSTEM_ADDR + EE_SECTION_SYSTEM_SIZE)

/* section shortcuts */
#define EE_SYS_ADDR                                                   (EE_SECTION_SYSTEM_ADDR)

/* Auralys system eeprom map */
#define EE_SYS_SIGNATURE_OFFS                                                    (EE_SYS_ADDR)
#define EE_SYS_SIGNATURE_SIZE                                                              (3)
#define EE_SYS_DESCRIPTOR_MJR                  (EE_SYS_SIGNATURE_OFFS + EE_SYS_SIGNATURE_SIZE)
#define EE_SYS_DESCRIPTOR_MJR_SIZE                                                         (1)
#define EE_SYS_DESCRIPTOR_MIN             (EE_SYS_DESCRIPTOR_MJR + EE_SYS_DESCRIPTOR_MJR_SIZE)
#define EE_SYS_DESCRIPTOR_MIN_SIZE                                                         (1)
#define EE_SYS_INIT_CONFIG_OFFS           (EE_SYS_DESCRIPTOR_MIN + EE_SYS_DESCRIPTOR_MIN_SIZE)
#define EE_SYS_INIT_CONFIG_SIZE                                                            (1)
#define EE_SYS_INIT_FLAG_OFFS              (EE_SYS_INIT_CONFIG_OFFS + EE_SYS_INIT_CONFIG_SIZE)
#define EE_SYS_INIT_FLAG_SIZE                                                              (1)
#define EE_SYS_INIT_YEAR_OFFS                  (EE_SYS_INIT_FLAG_OFFS + EE_SYS_INIT_FLAG_SIZE)
#define EE_SYS_INIT_YEAR_SIZE                                                              (1)
#define EE_SYS_INIT_MONTH_OFFS                 (EE_SYS_INIT_YEAR_OFFS + EE_SYS_INIT_YEAR_SIZE)
#define EE_SYS_INIT_MONTH_SIZE                                                             (1)
#define EE_SYS_INIT_DAY_OFFS                 (EE_SYS_INIT_MONTH_OFFS + EE_SYS_INIT_MONTH_SIZE)
#define EE_SYS_INIT_DAY_SIZE                                                               (1)
#define EE_HW_UNIT_TYPE_OFFS                     (EE_SYS_INIT_DAY_OFFS + EE_SYS_INIT_DAY_SIZE)
#define EE_HW_UNIT_TYPE_SIZE                                                               (1)
#define EE_HW_MKS_SLAVE_ADDR_OFFS                (EE_HW_UNIT_TYPE_OFFS + EE_HW_UNIT_TYPE_SIZE)
#define EE_HW_MKS_SLAVE_ADDR_SIZE                                                          (1)
#define EE_HW_MKS_SPEED_OFFS           (EE_HW_MKS_SLAVE_ADDR_OFFS + EE_HW_MKS_SLAVE_ADDR_SIZE)
#define EE_HW_MKS_SPEED_SIZE                                                               (1)
#define EE_HW_MKS_ACCEL_OFFS                     (EE_HW_MKS_SPEED_OFFS + EE_HW_MKS_SPEED_SIZE)
#define EE_HW_MKS_ACCEL_SIZE                                                               (1)

/* IMPORTANT: (EE_SYS_ADDR_END - EE_SYS_ADDR) < EE_SECTION_SYSTEM_SIZE, do not overflow     */
#define EE_SYS_ADDR_END                          (EE_HW_MKS_ACCEL_OFFS + EE_HW_MKS_ACCEL_SIZE)
/* */


/* BIT-MASKS for CONFIG fields */
#define EE_SYS_CFG_ORIENTATION_MSB_MSK                                                            (1<<0)
#define EE_SYS_CFG_ORIENTATION_LSB_MSK                                                            (1<<1)
#define EE_SYS_CFG_ORIENTATION_MSK       (EE_SYS_CFG_ORIENTATION_MSB_MSK|EE_SYS_CFG_ORIENTATION_LSB_MSK)
#define EE_SYS_CFG_WIFI_ENABLE_MSK                                                                (1<<2)
#define EE_SYS_CFG_NTP_ENABLE_MSK                                                                 (1<<3)
#define EE_SYS_CFG_GPS_ENABLE_MSK                                                                 (1<<4)
#define EE_SYS_CFG_NBIOT_ENABLE_MSK                                                               (1<<5)
#define EE_SYS_CFG_LORAWAN_ENABLE_MSK                                                             (1<<6)

/* BIT-MASKS for INIT fields */
#define EE_SYS_INIT_BSPINITIALIZED_MSK                                                            (1<<0)
#define EE_SYS_INIT_BSPACTIVATED_MSK                                                              (1<<1)

#endif
/* EOF */
