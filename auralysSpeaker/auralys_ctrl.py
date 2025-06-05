#!/usr/bin/env python3
"""Auralys Speaker 3D position control"""

import argparse
import logging
import sys
import asyncio
import yaml
import wget
import json
import subprocess
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
hL_mm=2500.0
dL_mm=600.0
maxL=600000.0
minL=600000.0
mks_L_step_mm = float(100000.0/145.0)

# right stand position and size
hR_mm=2500.0
dR_mm=600.0
maxR=600000.0
minR=600000.0
mks_R_step_mm = float(100000.0/140.0)

# front stand position and size
hF_mm=2500.0
dF_mm=1700.0
maxF=600000.0
minF=600000.0
mks_F_step_mm = float(100000.0/145.0)

mks_origin_x = 1050.0
mks_origin_y = 0.0
mks_origin_z = 1450.0


#
# DO NOT CHANGE DEFINES BELOW THIS LINE
# 

_ROOT_DIR = os.path.abspath(os.path.dirname(__file__))
_CFG_FILENAME = "auralys_ctrl_cfg.json"
_PARAM_LIST=["position", "speed", "accel", "zero"]

#
# Tools
#

def int_or_str(text):
    """Helper function for argument parsing."""
    try:
        return int(text)
    except ValueError:
        return text

def compute_cables_length(x,y,z):
    tmpF =math.sqrt((dF_mm-x)**2 + y**2)
    tmpL =math.sqrt((dL_mm-y)**2 + x**2)
    tmpR =math.sqrt((dR_mm+y)**2 + x**2)

    lengthF=math.sqrt(tmpF**2 + (hF_mm-z)**2)
    lengthL=math.sqrt(tmpL**2 + (hL_mm-z)**2)
    lengthR=math.sqrt(tmpR**2 + (hR_mm-z)**2)

    print(lengthL)
    print(lengthR)
    print(lengthF)

    return [lengthL,lengthR, lengthF]

#
# SET Commands
#
def set_position(x,y,z,type):
    print("X="+str(x))
    print("y="+str(y))
    print("z="+str(z))

    x=float(x)
    y=float(y)
    z=float(z)
    # COORD TYPE: absolute cartesian
    if("ac"):
        # SANITY CHECK: verify coord outside of limits
        if ( (abs(y)>=dL_mm) or (abs(y)>=dR_mm) or (x<0) or (abs(x)>=dF_mm) or (z<0) or (abs(z)>=(min([hF_mm,hR_mm,hL_mm]))) ):
            logger.error("Invalid coordinate value")
            return -1

        # SANITY CHECK: verify coord inside the triangle
        angleR_ref=math.atan(dF_mm/dR_mm)
        angleL_ref=math.atan(dF_mm/dL_mm)
        if(angleR_ref < math.atan(x/(dR_mm+y))) or (angleL_ref < math.atan(x/(dL_mm-y))):
            logger.error("Coordinate outside of boundaries")
            return -1

        [mks_originL, mks_originR, mks_originF]=compute_cables_length(float(mks_origin_x),float(mks_origin_y),float(mks_origin_z))

        [lengthL, lengthR, lengthF]=compute_cables_length(x,y,z)

        # COMPUTE CABLEs LENGTH
        print("ORIGINS:")
        print(mks_originF)
        print(mks_originL)
        print(mks_originR)

        print("RESULTS:")
        print(lengthF)
        print(lengthL)
        print(lengthR)

        print("RESULTS:")
        print((mks_originF-lengthF)*mks_F_step_mm)
        print((mks_originL-lengthL)*mks_L_step_mm)
        print((mks_originR-lengthR)*mks_R_step_mm)

    else:
        logger.error("Unsupported coordintate type: "+type)
        return -1

    return (0)

def set_select(args):
    rv=0

    if("position"==args.param[0]):
        try:
            [x,y,z]=list(args.param[1].strip().split(","))
        except:
            logger.error("Invalid coordinate format, should comma separated: x,y,z")
            return (-1)

        rv=set_position(x,y,z,args.type)
    
    return (rv)


#
# MAIN
#
if __name__ == "__main__":
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument(
        "-c",
        "--command",
        type=str,
        default=None,
        help="set/get/cmd command (default: %(default)s)",
    )

    parser.add_argument(
        "-p",
        "--param",
        type=str,
        nargs=2,
        default=[None,None],
        help="param name (default: %(default)s)",
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

    auralys_cfg={
        "hL_mm":hL_mm,
        "dL_mm":dL_mm,
        "maxL":maxL,
        "minL":minL,
        "hR_mm":hR_mm,
        "dR_mm":dR_mm,
        "maxR":maxR,
        "minR":minR,
        "hF_mm":hF_mm,
        "dF_mm":dF_mm,
        "maxF":maxF,
        "minF":minF,
        "coord_type":args.type,
    }

    with open(_ROOT_DIR+"/"+_CFG_FILENAME, "w") as outfile:
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

    # print(args)
    logger.info("-" * 80)

    #
    # sanity checks to validate input params
    #
    if(args.command==None):
        logger.error("Command missing.")
        exit(0)

    if(args.command=="set"):
        set_select(args)
    elif (args.command=="get"):
        get_select(args)
    elif (args.command=="cmd"):
        cmd_select(args)
    else:
        logger.error("Command invalid/unsupported.")
        exit(0)


    print("ciao.")