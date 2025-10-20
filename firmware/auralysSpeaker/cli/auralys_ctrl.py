#!/usr/bin/env python3
"""Auralys Speaker 3D position control"""

import argparse
import logging
import sys
import asyncio
import yaml

# import wget
import requests
import multiprocessing
import json
import subprocess
import multiprocess
import time
import math
import os
import numpy as np


logger = logging.getLogger(__name__)


#
# DEFINES / CONSTANT / GLOBALS
#

# define the size for the speaker support (triangle shape)
# main origin "O is in the center of the "d" side
#
#          (L)
#           |
#           dL
#           |
#          (O)-----dF----(F)
#           |
#           dR
#           |
#          (R)

# left stand position and size
hL_mm = 3000.0
dL_mm = 600.0
maxL = 600000.0
minL = -700000.0
mks_L_step_mm = float(1000000.0 / 1570.0)

# right stand position and size
hR_mm = 3000.0
dR_mm = 600.0
maxR = 600000.0
minR = -700000.0
mks_R_step_mm = float(1000000.0 / 1600.0)

# front stand position and size
hF_mm = 3000.0
dF_mm = 1540.0
maxF = 700000.0
minF = -800000.0
mks_F_step_mm = float(1000000.0 / 1505.0)

# cartesian coord min/max
min_x_cartesian = 400
max_x_cartesian = dF_mm - 100
min_y_cartesian = -(dR_mm - 100)
max_y_cartesian = dL_mm - 100
min_z_cartesian = 400
max_z_cartesian = min(hL_mm, hR_mm, hF_mm) - 100

# origin (zero point) for MKS steppers
mks_origin_x_mm = 700.0
mks_origin_y_mm = 0.0
mks_origin_z_mm = 1300.0

# origin (zero point) for head centroid
head_origin_x_mm = 0
head_origin_y_mm = 0
head_origin_z_mm = 1680

# ip_addresses of the auralys units
ip_addr_L = "192.168.10.32"  # left stand
ip_addr_R = "192.168.10.34"  # right stand
ip_addr_F = "192.168.10.240"  # center stand
ip_addr_S = "192.168.10.178"  # rotating speaker
ip_addr_T = "192.168.10.96"  # rotating table

# speaker stepping
mks_S_step_deg = float(4200 / 90)

# rotating table stepping
mks_T_step_deg = float(2454840 / 360)


#
# ##################################################################################### #
# DO NOT CHANGE DEFINES BELOW THIS LINE
# ##################################################################################### #
#

_ROOT_DIR = os.path.abspath(os.path.dirname(__file__))
_CFG_FILENAME = "auralys_ctrl_cfg.json"
_SET_PARAM_LIST = ["position", "speed", "accel"]
_GET_PARAM_LIST = ["position", "speed", "accel"]
_COORD_TYPE_DICT = {
    "ac": "absolute, cartesian",
    "as": "absolute, spherical",
    "rc": "relative, cartesian",
    "rs": "relative, spherical",
}
_CMD_LIST = ["gozero", "setzero", "stop"]

# speaker rotation
_SPEAKER_ROTATION_CCW = 1
_SPEAKER_ROTATION_MAX = 80
_SPEAKER_ROTATION_MIN = -80
_SPEAKER_ROTATION_STEP_MAX = _SPEAKER_ROTATION_MAX * mks_S_step_deg
_SPEAKER_ROTATION_STEP_MIN = _SPEAKER_ROTATION_MIN * mks_S_step_deg


# rotating table rotation
_TABLE_ROTATION_CCW = 0
_TABLE_ROTATION_MAX = 360
_TABLE_ROTATION_MIN = -360
_TABLE_ROTATION_STEP_MAX = _TABLE_ROTATION_MAX * mks_T_step_deg
_TABLE_ROTATION_STEP_MIN = _TABLE_ROTATION_MIN * mks_T_step_deg


#
# Tools
#


def int_or_str(text):
    """Helper function for argument parsing."""
    try:
        return int(text)
    except ValueError:
        return text


def compute_wires_length(x, y, z):
    tmpF = math.sqrt((dF_mm - x) ** 2 + y**2)
    tmpL = math.sqrt((dL_mm - y) ** 2 + x**2)
    tmpR = math.sqrt((dR_mm + y) ** 2 + x**2)

    lengthF = math.sqrt(tmpF**2 + (hF_mm - z) ** 2)
    lengthL = math.sqrt(tmpL**2 + (hL_mm - z) ** 2)
    lengthR = math.sqrt(tmpR**2 + (hR_mm - z) ** 2)

    return [lengthL, lengthR, lengthF]


def verify_coord_limits(x, y, z):
    # SANITY CHECK: verify coord outside of limits
    if (
        (abs(y) >= dL_mm)
        or (abs(y) >= dR_mm)
        or (x < 0)
        or (abs(x) >= dF_mm)
        or (z < 0)
        or (abs(z) >= (min([hF_mm, hR_mm, hL_mm])))
    ):
        logger.error("Invalid coordinate value")
        return -1

    # SANITY CHECK: verify coord inside the triangle
    angleR_ref = math.atan(dF_mm / dR_mm)
    angleL_ref = math.atan(dF_mm / dL_mm)
    if (angleR_ref < math.atan(x / (dR_mm + y))) or (angleL_ref < math.atan(x / (dL_mm - y))):
        logger.error("Coordinate outside of boundaries")
        return -1

    return 0


def verify_coord_cartesian_limits(x, y, z):
    if (
        (x > max_x_cartesian)
        or (x < min_x_cartesian)
        or (z > max_z_cartesian)
        or (z < min_z_cartesian)
        or (y > max_y_cartesian)
        or (y < min_y_cartesian)
    ):
        return -1

    return 0


def mks_set_length(ip_addr, mks_length):
    url = "http://" + str(ip_addr) + "/position/set/"
    response = requests.post(url, data=str(int(mks_length)))
    result = json.loads(response.text)
    if result["error"] != 0:
        return -1

    return 0


def mks_get_status(ip_addr, option):
    url = "http://" + str(ip_addr) + "/status/get/"
    response = requests.get(url)

    result = json.loads(response.text)
    if result["error"] != 0:
        return -1

    return result["status"]


def mks_set_zero(ip_addr, option):
    url = "http://" + str(ip_addr) + "/position/zero/set/"
    response = requests.post(url, data=str(int(option)))
    result = json.loads(response.text)
    if result["error"] != 0:
        return -1

    return 0


def mks_get_inclinometer(ip_addr, option):
    url = "http://" + str(ip_addr) + "/status/get/"
    response = requests.get(url)

    result = json.loads(response.text)
    if result["error"] != 0:
        return -1

    return (result["status"], [result["accel"]["x"], result["accel"]["y"], result["accel"]["z"]])


def mks_rotate_table(mks_degree):
    position_step = mks_degree * mks_T_step_deg

    if _TABLE_ROTATION_CCW:
        position_step *= -1

    if (position_step > _TABLE_ROTATION_STEP_MIN) and (position_step < _TABLE_ROTATION_STEP_MAX):
        mks_set_position(ip_addr_T, int(position_step))


def mks_rotate_speaker(mks_degree):
    #########
    # STEP #1: read inclinometer 3 times for average
    logger.info("mks_rotate_speaker: read inclinometer.")

    acc = []

    status = 0

    while (status == 0) and (len(acc) < 3):
        time.sleep(0.5)
        status, accel = mks_get_inclinometer(ip_addr_S, 0)
        acc.append(accel[1])

    if status != 0:
        logger.error("mks_rotate_speaker: error while getting status.")
        return -1

    acc_sum = 0
    for x in acc:
        acc_sum += x

    x = acc_sum / len(acc)

    angle = 90 - math.degrees(math.acos(x / 9.8))

    angle = angle - mks_degree

    # if( _SPEAKER_ROTATION_CCW ):
    #     angle = angle - mks_degre
    # else:
    #     angle = angle +mks_degree

    position_step = angle * mks_S_step_deg

    if _SPEAKER_ROTATION_CCW:
        position_step *= -1

    if (position_step > _SPEAKER_ROTATION_STEP_MIN) and (position_step < _SPEAKER_ROTATION_STEP_MAX):
        mks_set_position(ip_addr_S, position_step)


def mks_set_position(ip_addr, mks_position):
    rv = 0

    logger.info("mks_set_position, value: " + str(mks_position))

    #########
    # STEP #0: GET current position and verify status
    logger.info("mks_set_position: get current status.")

    err = mks_get_status(ip_addr, 0)

    if err != 0:
        logger.error("mks_set_position: error while executing GET POSITION")

    #########
    # STEP #1: SET current position and verify status
    logger.info("mks_set_position: positioning started.")

    err = mks_set_length(ip_addr, mks_position)

    if err != 0:
        logger.error("mks_set_position: error while executing SET POSITION")

    #########
    # STEP #2: monitor & wait until position is done
    logger.info("mks_set_position: wait/veryfy position completed.")

    if err == 0:
        status = 1
        while (status != 0) and (status != -1):
            time.sleep(1)

            status = mks_get_status(ip_addr, 0)

            if status == -1:
                logger.error("mks_set_position: error while positioning.")
            else:
                logger.info("mks_set_position: positioning done.")

    # return negative on error. zero on position completed
    rv = 0
    if status != 0:
        rv = -1

    return rv


def mks_set_positions(mks_position_F, mks_position_L, mks_position_R):
    rv = 0

    logger.info("mks_set_positions, mks_F: " + str(mks_position_F))
    logger.info("mks_set_positions, mks_L: " + str(mks_position_L))
    logger.info("mks_set_positions, mks_R: " + str(mks_position_R))

    #########
    # STEP #0: GET current position and verify status
    logger.info("mks_set_positions: get current status.")

    task_args = [(ip_addr_F, mks_position_F), (ip_addr_L, mks_position_L), (ip_addr_R, mks_position_R)]

    with multiprocessing.Pool(processes=3) as pool:
        results = pool.starmap(mks_get_status, task_args)

    # check result for errors
    err = 0
    for result in results:
        err += result

    if err != 0:
        logger.error("mks_set_positions: error while executing GET POSITION")

    #########
    # STEP #1: SET current position and verify status
    logger.info("mks_set_positions: positioning started.")

    task_args = [(ip_addr_F, mks_position_F), (ip_addr_L, mks_position_L), (ip_addr_R, mks_position_R)]

    with multiprocessing.Pool(processes=3) as pool:
        results = pool.starmap(mks_set_length, task_args)

    # check result for errors
    err = 0
    for result in results:
        err += result

    if err != 0:
        logger.error("mks_set_positions: error while executing SET POSITION")

    #########
    # STEP #2: monitor & wait until position is done
    logger.info("mks_set_positions: wait/veryfy position completed.")

    task_args = [(ip_addr_F, mks_position_F), (ip_addr_L, mks_position_L), (ip_addr_R, mks_position_R)]

    if err == 0:
        status = 1
        while (status != 0) and (status != -1):
            time.sleep(1)

            with multiprocessing.Pool(processes=3) as pool:
                results = pool.starmap(mks_get_status, task_args)

            # check result for errors
            result_sum = 0
            for result in results:
                if result == -1:
                    logger.error("mks_set_positions: error while positioning.")
                    status = -1
                result_sum += result
            if result_sum == 0:
                logger.info("mks_set_positions: positioning done.")
                status = 0

    # return negative on error. zero on position completed
    rv = 0
    if status != 0:
        rv = -1

    return rv


#
# SET Commands
#
def set_position(x, y, z, type):
    rv = 0
    x = float(x)
    y = float(y)
    z = float(z)

    # COORD TYPE: absolute cartesian
    if "ac" == type:
        # SANITY CHECK
        if 0 != verify_coord_limits(x, y, z):
            logger.error("coordinates verification failed.")
            return -1

        if 0 != verify_coord_cartesian_limits(x, y, x):
            logger.error("coordinates verification failed.")
            return -1

        [mks_originL, mks_originR, mks_originF] = compute_wires_length(
            float(mks_origin_x_mm), float(mks_origin_y_mm), float(mks_origin_z_mm)
        )

        [lengthL, lengthR, lengthF] = compute_wires_length(x, y, z)

        logger.info("set_position, F: " + str(lengthF))
        logger.info("set_position, L: " + str(lengthL))
        logger.info("set_position, R: " + str(lengthR))

        mks_position_F = (mks_originF - lengthF) * mks_F_step_mm
        mks_position_L = (mks_originL - lengthL) * mks_L_step_mm
        mks_position_R = (mks_originR - lengthR) * mks_R_step_mm

        logger.info("set_position, mks_F: " + str(mks_position_F))
        logger.info("set_position, mks_L: " + str(mks_position_L))
        logger.info("set_position, mks_R: " + str(mks_position_R))

        if (
            ((mks_position_F > maxF) or (mks_position_F < minF))
            or ((mks_position_R > maxR) or (mks_position_R < minR))
            or ((mks_position_L > maxL) or (mks_position_L < minL))
        ):
            logger.error("set_position: wire lengths outside of limits")
            return -1

        rv = mks_set_positions(mks_position_F, mks_position_L, mks_position_R)

    elif "rs" == type:
        print("relative spherical")

    else:
        if type in _COORD_TYPE_DICT:
            logger.error("Not implemented coordintate type, " + type + " [" + _COORD_TYPE_DICT[type] + "]")
        else:
            logger.error("Unsupported coordintate type: " + type)
        return -1

    return rv


def set_select(args):
    rv = 0

    if "position" == args.command[1]:
        try:
            [x, y, z] = list(args.param[0].strip().split(","))
        except:
            logger.error("Invalid coordinate format, should comma separated: x,y,z")
            return -1
        rv = set_position(x, y, z, args.type)
    else:
        logger.error("unsupported SET option")
        rv = -1

    return rv


#
# GET Commands
#


def get_select(args):
    rv = 0

    logger.error("GET not yet implemented. exit.")

    return rv


#
# CMD Commands
#
def cmd_setzero():
    task_args = [(ip_addr_F, 0), (ip_addr_L, 0), (ip_addr_R, 0), (ip_addr_S, 0)]

    with multiprocessing.Pool(processes=4) as pool:
        results = pool.starmap(mks_set_zero, task_args)

    # check result for errors
    err = 0
    for result in results:
        err += result

    if err != 0:
        logger.error("mks_set_positions: error while executing SET POSITION")
        return -1

    return 0


def cmd_select(args):
    rv = 0

    if "gozero" == args.command[1]:
        rv = set_position(mks_origin_x_mm, mks_origin_y_mm, mks_origin_z_mm, "ac")
    elif "setzero" == args.command[1]:
        rv = cmd_setzero()
    else:
        logger.error("unsupported CMD option")
        rv = -1

    return rv


#
# MAIN
#
if __name__ == "__main__":
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument(
        "-c",
        "--command",
        type=str,
        nargs=2,
        default=None,
        help="set/get/cmd command (default: %(default)s)",
    )

    parser.add_argument(
        "-p",
        "--param",
        type=str,
        nargs=1,
        default=None,
        help="param name (default: %(default)s)",
    )

    parser.add_argument(
        "-rs",
        "--rspeaker",
        type=int,
        nargs=1,
        help=f"rotate speaker [{_SPEAKER_ROTATION_MAX} | {_SPEAKER_ROTATION_MIN}] ",
    )

    parser.add_argument(
        "-rt",
        "--rtable",
        type=int,
        nargs=1,
        help=f"rotate turning table [{_SPEAKER_ROTATION_MAX} | {_SPEAKER_ROTATION_MIN}] ",
    )

    parser.add_argument(
        "-t",
        "--type",
        type=str,
        default="as",
        help="coord type, a:abs, r:rel, c:cartesian, s:spherical (default: %(default)s)",
    )

    parser.add_argument(
        "-o", "--output_device", type=int_or_str, default=None, help="output device (numeric ID or substring)"
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        default=False,
        help="verbose (default: %(default)s)",
    )

    args, remaining = parser.parse_known_args()

    #
    # set debug verbosity
    #
    if args.verbose:
        logging.basicConfig(level=logging.INFO)
    else:
        logging.basicConfig(level=logging.WARNING)

    #
    # set config
    #

    auralys_cfg = {
        "hL_mm": hL_mm,
        "dL_mm": dL_mm,
        "maxL": maxL,
        "minL": minL,
        "hR_mm": hR_mm,
        "dR_mm": dR_mm,
        "maxR": maxR,
        "minR": minR,
        "hF_mm": hF_mm,
        "dF_mm": dF_mm,
        "maxF": maxF,
        "minF": minF,
        "coord_type": args.type,
    }

    with open(_ROOT_DIR + "/" + _CFG_FILENAME, "w") as outfile:
        outfile.write(json.dumps(auralys_cfg, indent=4))

    #
    # load params from external config file (if given)
    #
    # yaml_params = vars(args)
    # if args1.yaml_params != None:
    #     # local copy for override later
    #     params = vars(args)

    #     # load from config file
    #     try:
    #         with open(args1.yaml_params, "r") as file:
    #             yaml_params = yaml.safe_load(file)
    #     except:
    #         sys.exit("\n[ERROR] cannot open/parse yaml config file: {}".format(args1.yaml_params))

    #     # sanity check: config file sintax name version
    #     if yaml_params["syntax"]["name"] != CONFIG_SYNTAX_NAME:
    #         sys.exit(
    #             "\n[ERROR] invalid syntax name for MAP yaml config file: expected [{}] got [{}]".format(
    #                 CONFIG_SYNTAX_NAME, yaml_params["syntax"]["name"]
    #             )
    #         )

    #     # sanity check: config file sintax minimum supported version number
    #     if CONFIG_SYNTAX_VERSION_MIN > (
    #         yaml_params["syntax"]["version"]["major"] + yaml_params["syntax"]["version"]["minor"] / 10
    #     ):
    #         sys.exit(
    #             "\n[ERROR] invalid syntax version ({}) for map yaml config file, expected:{}".format(
    #                 (yaml_params["syntax"]["version"]["major"] + yaml_params["syntax"]["version"]["minor"] / 10),
    #                 CONFIG_SYNTAX_VERSION_MIN,
    #             )
    #         )

    #     # params override: console params must have priority on config file (explicit parameter setting)
    #     for p in params:
    #         if (p in yaml_params) and (params[p] != None):
    #             yaml_params[p] = params[p]

    #
    # setup log
    #
    logger.info("-" * 80)
    logger.info("SETUP:")
    logger.info("-" * 80)
    if args.verbose:
        print(args)
    logger.info("-" * 80)

    #
    # sanity checks to validate input params
    #

    if args.command != None:
        if args.command[0] == "set":
            set_select(args)
        elif args.command[0] == "get":
            get_select(args)
        elif args.command[0] == "cmd":
            cmd_select(args)
        else:
            logger.error("Command invalid/unsupported.")
            exit(0)
    #
    # check for speaker rotation
    #
    if args.rspeaker:
        if (args.rspeaker[0] < _SPEAKER_ROTATION_MAX) and (args.rspeaker[0] > _SPEAKER_ROTATION_MIN):
            mks_rotate_speaker(args.rspeaker[0])
        else:
            logger.error("speaker rotation outside of boundaries")

    #
    # check for rotating_table rotation
    #
    if args.rtable:
        if (args.rtable[0] < _TABLE_ROTATION_MAX) and (args.rtable[0] > _TABLE_ROTATION_MIN):
            mks_rotate_table(args.rtable[0])
        else:
            logger.error("rotating-table rotation outside of boundaries")

    logger.info("done.")
