#!/usr/bin/env python3
"""Read compute_hrir results and save SOFA file (Spatially Oriented Format for Acoustics)"""

from __future__ import division
import scipy.signal as sig

import os
import re
import sys
import glob
import yaml
import logging
import signal
import argparse

import matplotlib
import matplotlib.pyplot as plt
import matplotlib.mlab as mlab
import argparse
import sys

import numpy as np
import pyfar as pf
import soundfile as sf
import sofar as sof
from multiprocessing import Pool
from setproctitle import setproctitle

from datetime import datetime


logger = logging.getLogger(__name__)


def show_sofa(yaml_params):
    try:
        data_ir, source_coordinates, receiver_coordinates = pf.io.read_sofa(yaml_params["measure_file"])
    except:
        logger.error("cannot read sofa file:{}".format(yaml_params["measure_file"]))
        return

    if yaml_params["graphs"] != "skip":
        if yaml_params["show_sources_coordinates"]:
            source_coordinates.show()
            plt.show()

        if yaml_params["show_receivers_coordinates"]:
            receiver_coordinates.show()
            plt.show()

        if yaml_params["show_selected_source"]:
            print(yaml_params["show_selected_source"])

            tmp = yaml_params["show_selected_source"].split(",")

            if len(tmp) == 3:
                # Lets find the HRIR for the source position at the left ear on the horizontal plane. It has an azimuth angle of 90 degrees and an elevation of 0 degrees
                index, *_ = source_coordinates.find_nearest_k(
                    int(tmp[0]),
                    int(tmp[1]),
                    int(tmp[2]),
                    k=1,
                    domain="sph",
                    convention="top_elev",
                    unit="deg",
                    show=True,
                )

                _, mask = source_coordinates.find_slice("elevation", unit="deg", value=0, show=True)

                if yaml_params["show_selected_receiver"] == "all":
                    pf.plot.time_freq(data_ir[index])
                    plt.show()
                else:
                    try:
                        rx_id = int(yaml_params["show_selected_receiver"])
                        pf.plot.time_freq(data_ir[index][rx_id])
                        plt.show()
                    except:
                        logger.error("invalid receiver number")

            else:
                logger.error("invalid source coordinates")


#
###############################################################################
# MAIN
###############################################################################
#

if __name__ == "__main__":
    # set user friendly process name for MAIN
    setproctitle("comp_sofa_main")

    # parse input params
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("-l", "--list_folders", action="store_true", help="show list of available sessions")
    parser.add_argument(
        "-yp",
        "--yaml_params",
        type=str,
        default=None,
        help="yaml input params file (default: %(default)s)",
    )

    args1, remaining = parser.parse_known_args()

    #
    # check if we just want to list folders and quit
    #
    if args1.list_folders:
        sofa_file_list = []

        # search for available sofa files
        sofa_file_list = glob.glob("**/*.sofa", recursive=True)

        if len(sofa_file_list) > 0:
            print("listing available SOFA audio files:")
            print("========================================")
            for s in sofa_file_list:
                print(s)
        else:
            print("no audio measures found.")
        parser.exit(0)

    #
    # do we have a config file? if yes parse WITHOUT defaults
    #
    if args1.yaml_params != None:
        parser = argparse.ArgumentParser(
            description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, parents=[parser]
        )
        parser.add_argument(
            "-mf",
            "--measure_file",
            type=str,
            help="SOFA file to open",
        )
        parser.add_argument(
            "-c",
            "--cpu_process",
            type=int,
            help="maximum number of CPU process to use",
        )
        parser.add_argument(
            "-g",
            "--graphs",
            type=str,
            help="skip, save, show, show_and_save",
        )
        parser.add_argument(
            "-ssc",
            "--show_sources_coordinates",
            action="store_true",
            help="show sources coordinates (default: %(default)s)",
        )
        parser.add_argument(
            "-src",
            "--show_receivers_coordinates",
            action="store_true",
            help="show receivers coordinates (default: %(default)s)",
        )
        parser.add_argument(
            "-sss",
            "--show_selected_source",
            type=str,
            help="show impulse response for selected source, shperical coordinates (default: %(default)s)",
        )
        parser.add_argument(
            "-ssr",
            "--show_selected_receiver",
            type=str,
            help="show impulse response for selected receiver on selected source, trackid or all (default: %(default)s)",
        )

    #
    # no config, use defaults
    #
    else:
        parser = argparse.ArgumentParser(
            description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, parents=[parser]
        )
        parser.add_argument(
            "-mf",
            "--measure_file",
            type=str,
            default=None,
            help="SOFA file to open",
        )
        parser.add_argument(
            "-c",
            "--cpu_process",
            default=6,
            type=int,
            help="maximum number of CPU process to use",
        )
        parser.add_argument(
            "-g",
            "--graphs",
            type=str,
            default="show",
            help="skip, save, show, show_and_save (default: %(default)s)",
        )
        parser.add_argument(
            "-ssc",
            "--show_sources_coordinates",
            action="store_true",
            default=False,
            help="show sources coordinates (default: %(default)s)",
        )
        parser.add_argument(
            "-src",
            "--show_receivers_coordinates",
            action="store_true",
            default=False,
            help="show receivers coordinates (default: %(default)s)",
        )
        parser.add_argument(
            "-sss",
            "--show_selected_source",
            default="0,0,1",
            type=str,
            help="show impulse response for selected source, shperical coordinates (default: %(default)s)",
        )
        parser.add_argument(
            "-ssr",
            "--show_selected_receiver",
            default="all",
            type=str,
            help="show impulse response for selected receiver on selected source, trackid or all (default: %(default)s)",
        )

    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        default=False,
        help="verbose (default: %(default)s)",
    )
    parser.add_argument(
        "-log",
        "--logfile",
        type=str,
        default=None,
        help="log verbose output to file (default: %(default)s)",
    )

    args, remaining = parser.parse_known_args(remaining)

    #
    # set debug verbosity
    #
    if args.verbose:
        if args.logfile != None:
            logging.basicConfig(filename=args.logfile, encoding="utf-8", level=logging.INFO)
        else:
            logging.basicConfig(level=logging.INFO)
    else:
        logging.basicConfig(level=logging.WARNING)

    #
    # load params from external config file (if given)
    #
    yaml_params = vars(args)
    if args1.yaml_params != None:
        params = vars(args)
        try:
            with open(args1.yaml_params, "r") as file:
                yaml_params = yaml.safe_load(file)
        except:
            sys.exit("\n[ERROR] cannot open/parse yaml config file: {}".format(args1.yaml_params))

        # console params have priority on default config
        params = vars(args)
        for p in params:
            if (p in yaml_params) and (params[p] != None):
                yaml_params[p] = params[p]

    #
    # deallocate args
    #
    args1 = []
    args = []

    #
    # set graphs computation level
    #
    if yaml_params["graphs"].lower() == "skip":
        _PLOT_SAVE_GRAPH = 0
    elif yaml_params["graphs"].lower() == "save":
        _PLOT_SAVE_GRAPH = 1
    elif yaml_params["graphs"].lower() == "show":
        _PLOT_SAVE_GRAPH = 2
    elif yaml_params["graphs"].lower() == "show_and_save":
        _PLOT_SAVE_GRAPH = 3
    else:
        _PLOT_SAVE_GRAPH = 0  # skip by default

    # matplotlib to allow saving graphs
    if _PLOT_SAVE_GRAPH < 2:
        matplotlib.use("Agg")

    #
    # setup log
    #
    logger.info("-" * 80)
    logger.info("SETUP:")
    logger.info("-" * 80)

    for p in yaml_params:
        logger.info("{} : {}".format(str(p), str(yaml_params[p])))

    #
    # show sofa details
    #
    if yaml_params["verbose"]:
        try:
            sofa = sof.read_sofa(yaml_params["measure_file"])
            sofa.inspect()
            sofa.verify()
        except:
            logger.error("[ERROR] cannot read file {}".format(yaml_params["measure_file"]))

    #
    # show plots
    #
    show_sofa(yaml_params)
