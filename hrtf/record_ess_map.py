#!/usr/bin/env python3
"""audio measure map for rotating table"""

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

import record_ess

import numpy as np
import sounddevice as sd

import logging

logger = logging.getLogger(__name__)


def int_or_str(text):
    """Helper function for argument parsing."""
    try:
        return int(text)
    except ValueError:
        return text


#
# DEFINES / CONSTANT / GLOBALS
#
_ROOT_DIR = os.path.abspath(os.path.dirname(__file__))

CONFIG_SYNTAX_NAME = "audio_measure_map"
CONFIG_SYNTAX_VERSION_MIN = 0.1

ESS_CONFIG_SYNTAX_NAME = "audio_measure"
ESS_CONFIG_SYNTAX_VERSION_MIN = 0.1
ESS_CONFIG_COORD_ROUND_DECIMALS = 9


def update_ess_yaml_params(yaml_params=[], azimuth=0, elevation=0, distance=1):
    result = {}
    result["error"] = 0

    # check: config file sintax name version
    if yaml_params["syntax"]["name"] != ESS_CONFIG_SYNTAX_NAME:
        result["error"] = -1

    #
    # For value definition see AES69-2022 in D.13 as per SingleRoomSRIR convention
    # where the Listener is placed into the origin position [0,0,0] in the center of the rooom
    #

    # update listener position coordinates
    # note: there shall be only one listener as per AES69-2022
    yaml_params["setup"]["listeners"][0]["position"]["coord"]["type"] = "cartesian"
    yaml_params["setup"]["listeners"][0]["position"]["coord"]["units"] = ["metre"]
    yaml_params["setup"]["listeners"][0]["position"]["coord"]["value"] = [0, 0, 0]
    yaml_params["setup"]["listeners"][0]["position"]["view_vect"]["value"] = [1, 0, 0]
    yaml_params["setup"]["listeners"][0]["position"]["up_vect"]["value"] = [0, 0, 1]

    # update source position coordinates based on given azimuth/elevation/distance
    # note: there shall be only one source as per AES69-2022
    # note: the origin of the spherical coordinate system is centered in the origin
    # of the room (both catesian and spherical are colocated for source/listener localization)
    # see AES69-2022 at 4.3.1 "Global Coordinate System"

    if 0:
        yaml_params["setup"]["sources"][0]["position"]["coord"]["type"] = "cartesian"
        yaml_params["setup"]["sources"][0]["position"]["coord"]["units"] = ["meter"]
        x = round(
            distance * math.cos(math.pi / 180 * (elevation % 360)) * math.cos(math.pi / 180 * (azimuth % 360)),
            ESS_CONFIG_COORD_ROUND_DECIMALS,
        )
        y = round(
            distance * math.cos(math.pi / 180 * (elevation % 360)) * math.sin(math.pi / 180 * (azimuth % 360)),
            ESS_CONFIG_COORD_ROUND_DECIMALS,
        )
        z = round(distance * math.sin(math.pi / 180 * (elevation % 360)), ESS_CONFIG_COORD_ROUND_DECIMALS)
        yaml_params["setup"]["sources"][0]["position"]["coord"]["value"] = [x, y, z]
    else:
        yaml_params["setup"]["sources"][0]["position"]["coord"]["type"] = "spherical"
        yaml_params["setup"]["sources"][0]["position"]["coord"]["units"] = ["degree", "degree", "metre"]
        yaml_params["setup"]["sources"][0]["position"]["coord"]["value"] = [azimuth, elevation, distance]

    # also keep a copy in spherical coord for easier documentation (!)
    yaml_params["setup"]["sources"][0]["position_copy"]["coord"]["type"] = "spherical"
    yaml_params["setup"]["sources"][0]["position_copy"]["coord"]["units"] = ["degree", "degree", "metre"]
    yaml_params["setup"]["sources"][0]["position_copy"]["coord"]["value"] = [azimuth, elevation, distance]

    # when moving the source we keep it "focused" on the listener, so we have to adj view/up vectors
    yaml_params["setup"]["sources"][0]["position"]["view_vect"]["type"] = "cartesian"
    yaml_params["setup"]["sources"][0]["position"]["view_vect"]["units"] = ["meter"]

    x = round(
        math.cos(math.pi / 180 * ((180 + azimuth) % 360)) * math.cos(math.pi / 180 * (elevation % 360)),
        ESS_CONFIG_COORD_ROUND_DECIMALS,
    )
    y = round(
        math.sin(math.pi / 180 * ((180 + azimuth) % 360)) * math.cos(math.pi / 180 * (elevation % 360)),
        ESS_CONFIG_COORD_ROUND_DECIMALS,
    )
    z = round(math.sin(math.pi / 180 * (elevation % 360)), ESS_CONFIG_COORD_ROUND_DECIMALS)
    yaml_params["setup"]["sources"][0]["position"]["view_vect"]["value"] = [x, y, z]

    x = round(
        math.sin(math.pi / 180 * ((180 + azimuth) % 360)) * math.sin(math.pi / 180 * (elevation % 360)),
        ESS_CONFIG_COORD_ROUND_DECIMALS,
    )
    y = round(
        math.cos(math.pi / 180 * ((180 + azimuth) % 360)) * math.sin(math.pi / 180 * (elevation % 360)),
        ESS_CONFIG_COORD_ROUND_DECIMALS,
    )
    z = round(math.cos(math.pi / 180 * (elevation % 360)), ESS_CONFIG_COORD_ROUND_DECIMALS)
    yaml_params["setup"]["sources"][0]["position"]["up_vect"]["value"] = [x, y, z]

    # update emitter(s) position of the above source

    return result


#
# MAIN
#
if __name__ == "__main__":
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("-l", "--list-devices", action="store_true", help="show list of audio devices and exit")
    parser.add_argument(
        "-yp",
        "--yaml_params",
        type=str,
        default=None,
        help="yaml input params file (default: %(default)s)",
    )

    args1, remaining = parser.parse_known_args()

    #
    # check if we just want to list devices and quit
    #
    if args1.list_devices:
        print(sd.query_devices())
        parser.exit(0)

    #
    # do we have a config file? if "yes" parse command line params WITHOUT defaults
    #
    if args1.yaml_params != None:
        parser = argparse.ArgumentParser(
            description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, parents=[parser]
        )
        parser.add_argument(
            "-b",
            "--frequency_begin",
            type=int,
            help="frequency_start in Hz",
        )
        parser.add_argument(
            "-e",
            "--frequency_end",
            type=int,
            help="frequency_stop in Hz",
        )
        parser.add_argument(
            "-d",
            "--playback_duration",
            type=int,
            help="duration in seconds",
        )
        parser.add_argument(
            "-q",
            "--playback_prepadding",
            type=int,
            help="playback silence pre-padding in s",
        )
        parser.add_argument(
            "-p",
            "--playback_postpadding",
            type=int,
            help="playback silence post-padding in s",
        )
        parser.add_argument(
            "-s",
            "--samplerate",
            type=int,
            help="sampling rate in Hz",
        )
        parser.add_argument(
            "-r",
            "--repeat",
            type=int,
            help="sweep repetitions",
        )
        parser.add_argument(
            "-yc",
            "--ess_yaml_config",
            type=str,
            help="yaml config file",
        )
        parser.add_argument(
            "-m",
            "--measure_folder",
            type=str,
            help="measure output folder",
        )
        parser.add_argument(
            "-n",
            "--measure_name",
            type=str,
            help="measure output name",
        )
        parser.add_argument(
            "-eb",
            "--elevation_begin",
            type=int,
            help="rotation ELEVATION angle begin",
        )
        parser.add_argument(
            "-ee",
            "--elevation_end",
            type=int,
            help="rotation ELEVATION angle end",
        )
        parser.add_argument(
            "-es",
            "--elevation_step",
            type=int,
            help="rotation ELEVATION angle step",
        )
        parser.add_argument(
            "-ab",
            "--azimuth_begin",
            type=int,
            help="rotation AZIMUTH angle begin deg",
        )
        parser.add_argument(
            "-ae",
            "--azimuth_end",
            type=int,
            help="rotation AZIMUTH angle stop deg",
        )
        parser.add_argument(
            "-as",
            "--azimuth_step",
            type=int,
            help="rotation AZIMUTH angle step deg",
        )
        parser.add_argument(
            "-rtd",
            "--rtable_direction",
            type=str,
            help="rotating table direction (default: %(default)s)",
        )
        parser.add_argument("-aa", "--amplitude", type=float, help="audio amplitude level")

    #
    # no config, use defaults
    #
    else:
        parser = argparse.ArgumentParser(
            description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, parents=[parser]
        )
        parser.add_argument(
            "-b",
            "--frequency_begin",
            type=int,
            default=200,
            help="frequency_start in Hz (default: %(default)s)",
        )
        parser.add_argument(
            "-e",
            "--frequency_end",
            type=int,
            default=20000,
            help="frequency_stop in Hz (default: %(default)s)",
        )
        parser.add_argument(
            "-d",
            "--playback_duration",
            type=int,
            default=15,
            help="duration in seconds (default: %(default)s)",
        )
        parser.add_argument(
            "-q",
            "--playback_prepadding",
            type=int,
            default=2,
            help="playback silence pre-padding in s (default: %(default)s)",
        )
        parser.add_argument(
            "-p",
            "--playback_postpadding",
            type=int,
            default=2,
            help="playback silence post-padding in s (default: %(default)s)",
        )
        parser.add_argument(
            "-s",
            "--samplerate",
            type=int,
            default=96000,
            help="sampling rate in Hz (default: %(default)s)",
        )
        parser.add_argument(
            "-r",
            "--repeat",
            type=int,
            default=1,
            help="sweep repetitions (default: %(default)s)",
        )
        parser.add_argument(
            "-yc",
            "--ess_yaml_config",
            type=str,
            default="./ess_params.yaml",
            help="yaml config file for audio sweep recording (default: %(default)s)",
        )
        parser.add_argument(
            "-m",
            "--measure_folder",
            type=str,
            default="./",
            help="measure output folder (default: %(default)s)",
        )
        parser.add_argument(
            "-n",
            "--measure_name",
            type=str,
            default="ess_measure",
            help="measure output name (default: %(default)s)",
        )
        parser.add_argument(
            "-eb",
            "--elevation_begin",
            type=int,
            default=0,
            help="rotation ELEVATION angle begin (default: %(default)s) deg",
        )
        parser.add_argument(
            "-ee",
            "--elevation_end",
            type=int,
            default=0,
            help="rotation ELEVATION angle end (default: %(default)s) deg",
        )
        parser.add_argument(
            "-es",
            "--elevation_step",
            type=int,
            default=0,
            help="rotation ELEVATION angle step (default: %(default)s) deg",
        )
        parser.add_argument(
            "-ab",
            "--azimuth_begin",
            type=int,
            default=0,
            help="rotation AZIMUTH angle begin (default: %(default)s) deg",
        )
        parser.add_argument(
            "-ae",
            "--azimuth_end",
            type=int,
            default=350,
            help="rotation AZIMUTH angle end (default: %(default)s) deg",
        )
        parser.add_argument(
            "-as",
            "--azimuth_step",
            type=int,
            default=10,
            help="rotation AZIMUTH angle step (default: %(default)s) deg",
        )
        parser.add_argument(
            "-rtd",
            "--rtable_direction",
            type=str,
            default="ccw",
            help="rotating table direction (default: %(default)s)",
        )
        parser.add_argument(
            "-aa", "--amplitude", type=float, default=0.2, help="audio amplitude level (default: %(default)s)"
        )

    parser.add_argument(
        "-i", "--input_device", type=int_or_str, default=None, help="input device (numeric ID or substring)"
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

    parser.add_argument(
        "-t",
        "--test",
        action="store_true",
        default=False,
        help="dry-run for rotation testing (default: %(default)s)",
    )

    args, remaining = parser.parse_known_args(remaining)

    #
    # set debug verbosity
    #
    if args.verbose:
        logging.basicConfig(level=logging.INFO)
    else:
        logging.basicConfig(level=logging.WARNING)

    #
    # load params from external config file (if given)
    #
    yaml_params = vars(args)
    if args1.yaml_params != None:
        # local copy for override later
        params = vars(args)

        # load from config file
        try:
            with open(args1.yaml_params, "r") as file:
                yaml_params = yaml.safe_load(file)
        except:
            sys.exit("\n[ERROR] cannot open/parse yaml config file: {}".format(args1.yaml_params))

        # sanity check: config file sintax name version
        if yaml_params["syntax"]["name"] != CONFIG_SYNTAX_NAME:
            sys.exit(
                "\n[ERROR] invalid syntax name for MAP yaml config file: expected [{}] got [{}]".format(
                    CONFIG_SYNTAX_NAME, yaml_params["syntax"]["name"]
                )
            )

        # sanity check: config file sintax minimum supported version number
        if CONFIG_SYNTAX_VERSION_MIN > (
            yaml_params["syntax"]["version"]["major"] + yaml_params["syntax"]["version"]["minor"] / 10
        ):
            sys.exit(
                "\n[ERROR] invalid syntax version ({}) for map yaml config file, expected:{}".format(
                    (yaml_params["syntax"]["version"]["major"] + yaml_params["syntax"]["version"]["minor"] / 10),
                    CONFIG_SYNTAX_VERSION_MIN,
                )
            )

        # params override: console params must have priority on config file (explicit parameter setting)
        for p in params:
            if (p in yaml_params) and (params[p] != None):
                yaml_params[p] = params[p]

    #
    # deallocate args
    #
    args1 = []
    args = []

    #
    # setup log
    #
    logger.info("-" * 80)
    logger.info("SETUP:")
    logger.info("-" * 80)
    for p in yaml_params:
        logger.info("{} : {}".format(str(p), str(yaml_params[p])))

    #
    # sanity checks to validate input params
    #

    # I/O devices are mandatory
    if (yaml_params["input_device"] == None) or (yaml_params["output_device"] == None):
        sys.exit("\n[ERROR] invalid input/output device, see help for details.")

    # audio config file for sweep recording is mandatory
    ess_yaml_params = []
    if yaml_params["ess_yaml_config"] != None:
        try:
            with open(yaml_params["ess_yaml_config"], "r") as file:
                ess_yaml_params = yaml.safe_load(file)
        except:
            sys.exit(
                "\n[ERROR] cannot open/parse audio ESS yaml config file: {}".format(yaml_params["ess_yaml_config"])
            )

        # check: config file sintax name version
        if ess_yaml_params["syntax"]["name"] != ESS_CONFIG_SYNTAX_NAME:
            sys.exit(
                "\n[ERROR] invalid syntax name for ESS yaml config file: expected [{}] got [{}]".format(
                    ESS_CONFIG_SYNTAX_NAME, ess_yaml_params["syntax"]["name"]
                )
            )
    else:
        sys.exit("\n[ERROR] missing audio ESS yaml config file.")

    print(yaml_params)

    #
    # run measure loop for audio sweep recording
    #
    try:
        measure_name_bkp = yaml_params["measure_name"]

        # ToDo: no automation for elevation and distance loop
        #       only for azimuth on a measurement plane (rotating table)

        azimuth_current = yaml_params["azimuth_begin"]
        elevation_current = yaml_params["elevation_begin"]
        distance_current = yaml_params["distance_begin"]

        for angle in range(yaml_params["azimuth_begin"], yaml_params["azimuth_end"] + 1, yaml_params["azimuth_step"]):
            elevation_sign = "-"
            if elevation_current > 0:
                elevation_sign = "+"

            yaml_params["measure_name"] = measure_name_bkp + "_+{:03d}{}{:03d}+{:03d}_xAngle".format(
                angle, elevation_sign, abs(elevation_current), distance_current
            )

            logger.info("-" * 80)
            logger.info("ESS MAP: {}".format(yaml_params["measure_name"]))

            #
            # based on azimuth/elevation and distance we have to generate a proper ESS config file
            # we use a temporary file location since it is passed to the record_ess procedure which
            # will save the final config file into the audio recording folder
            #
            # We use convention "SingleRoomSRIR" where the Listener is placed into the origin position [0,0,0]
            #
            result = update_ess_yaml_params(
                yaml_params=ess_yaml_params, azimuth=angle, elevation=elevation_current, distance=distance_current
            )

            with open("/tmp/ess_params_000000.yaml", "w") as file:
                yaml.dump(ess_yaml_params, file)
                yaml_params["ess_yaml_config"] = "/tmp/ess_params_000000.yaml"

            #
            # run audio recording
            #

            #
            # adjust source azimuth based on rotating table direction
            #
            angle_adj = angle
            if yaml_params["rtable_direction"] == "ccw":
                angle_adj = (360 - int(angle)) % 360

            # debug only:
            # if result["error"] == 0:
            #     # time.sleep(1)
            #     record_ess.run_main(**yaml_params)
            # else:
            #     logger.error("[ERROR]: cannot set rotating table position, angle={}".format(angle_adj))

            # rotate table
            rv = subprocess.run(
                [_ROOT_DIR + "/cmd_set_position.sh", str(angle_adj)], stdout=subprocess.PIPE
            ).stdout.decode("utf-8")
            result = json.loads(rv)

            if result["error"] == 0:
                rv = subprocess.run([_ROOT_DIR + "/cmd_get_position.sh"], stdout=subprocess.PIPE).stdout.decode("utf-8")
                result = json.loads(rv)

                while result["position"] != angle_adj:
                    time.sleep(3)
                    rv = subprocess.run([_ROOT_DIR + "/cmd_get_position.sh"], stdout=subprocess.PIPE).stdout.decode(
                        "utf-8"
                    )
                    result = json.loads(rv)

                # rotating table position is now set: sleep 1s and start recording
                time.sleep(1)

                if not (yaml_params["test"]):
                    record_ess.run_main(**yaml_params)
            else:
                logger.error("[ERROR]: cannot set rotating table position, angle={}".format(angle_adj))

    except KeyboardInterrupt:
        sys.exit("\nInterrupted by user")
