
#ifndef _H_ILBERT_HWCONFIG_H_
#define _H_ILBERT_HWCONFIG_H_


/* ============================================================================= */
/* HARDWARE DESCRIPTION GLOBALS&DEFINES SECTION                                  */
/* ============================================================================= */
#define HW_ID_SIZE       (16)
#define HW_CODENAME_SIZE (16)
#define HW_CPU_ARCH_SIZE  (8)
#define HW_CPU_TYPE_SIZE  (8)

/* IMPORTANT: maximum size for hw descriptor is 256 bytes */
/* including WMARK (8bytes), and SW_DESCRIPTION section   */
/* see provisioning for details.                          */

/* HW_CONFIG_CURRENT SYNTAX VERSION: 0.3     */
/* 8 wmark + 172 hw + 27 sw = 207 of 256 max */

typedef struct _hw_config {
    uint8_t hw_section_size;
    uint8_t hw_descriptor_mjr;
    uint8_t hw_descriptor_min;
    char hw_codename[HW_CODENAME_SIZE + 1];
    char hw_cpu_arch[HW_CPU_ARCH_SIZE + 1];
    char hw_cpu_type[HW_CPU_TYPE_SIZE + 1];
    uint8_t hw_pcb_ver_mjr;
    uint8_t hw_pcb_ver_min;
    char hw_pcb_uuid4[32 + 1];
    uint8_t hw_unit_type;
    uint8_t hw_unit_orientation;
    uint8_t hw_mks_slave_addr;
    uint8_t hw_mks_speed;
    uint8_t hw_mks_accel;
}HW_PCB_CONFIG_T;


#endif
/* EOF */


/* 
===============================================================
DETAILS:
===============================================================
*/

#define HW_UNIT_TYPE_NONE                    (0)
#define HW_UNIT_TYPE_LEFT                    (1)
#define HW_UNIT_TYPE_RIGHT                   (2)
#define HW_UNIT_TYPE_FRONT                   (3)
#define HW_UNIT_TYPE_SPEAKER                 (4)

#define HW_UNIT_ORIENTATION_VERTICAL_UP      (0)
#define HW_UNIT_ORIENTATION_VERTICAL_DW      (1)
#define HW_UNIT_ORIENTATION_FLAT             (2)
