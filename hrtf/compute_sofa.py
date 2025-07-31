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


import multiprocessing
import multiprocessing.pool

from setproctitle import setproctitle

from datetime import datetime


logger = logging.getLogger(__name__)


#
# DEFINES / CONSTANT / GLOBALS
#
_CTRL_EXIT_SIGNAL = 0  # driven by CTRL-C, 0 to exit threads

_MIN_CPU_COUNT = 1  # we need at least one CPU for each compute process
_MIN_MEM_GB = 2  # min amount of memory for each compute process
_MAX_MEM_GB = 6  # max amount of memory for each compute process
_PLOT_SAVE_GRAPH = 0  # 0:skip, 1:save, 2:show, 3:show&save plot

# IR_INFO for pyfar data storage
_IR_INFO_DELAY = 0
_IR_INFO_DELAY_SAMPLES = 1
_IR_INFO_dbFS_CALIB = 2
_IR_INFO_SAMPLERATE = 3


#
# TOOLS
#
def int_or_str(text):
    """Helper function for argument parsing."""
    try:
        return int(text)
    except ValueError:
        return text


def signal_handler(sig, frame):
    global _CTRL_EXIT_SIGNAL

    print("\npressed Ctrl+C\n")
    _CTRL_EXIT_SIGNAL = 1
    # sys.exit(0)


#
# COMPUTE FUNCTIONS
#
# def read_ir_sofa(data=None):
#     sofa = None
#     folder = None

#     try:
#         (sofa, folder) = data
#     except:
#         logger.error("wrong data input")

#     logger.info("read_ir_sofa: {}".format(folder))

#     # # add IR data
#     # sofa.Data_IR[0, 0, :] = ir_processed.time[0]
#     # sofa.Data_IR[0, 1, :] = ir_processed.time[0]

#     # sofa.verify()

#     # sofa.inspect()


def sum_array(data=None):
    rv = 0

    items_num = len(data)
    for val in data:
        rv += val

    return rv


def compute_delay(data=None):
    adata = abs(data)

    peak_idx = np.argmax(adata)
    peak = adata[peak_idx]

    i = peak_idx - 4
    while (i > 4) and (sum_array(adata[i - 4 : i]) > (peak / 4)):
        i -= 1

    return i


def compute_delay_adj(data=None, idx=0):
    adata = abs(data)

    peak_idx = idx

    if peak_idx == 0:
        peak_idx = np.argmax(adata)

    peak = adata[peak_idx]

    i = peak_idx - 4
    while (i > 4) and (sum_array(adata[i - 4 : i]) > (peak / 4)):
        i -= 1

    return i


def read_ir_delays(data=None, configs=None, folders=None):
    global _CTRL_EXIT_SIGNAL

    err = 0
    samples_ir = 0
    samples_ir_window = 0

    for i in range(len(configs)):
        for ii in range(configs[i]["setup"]["listeners"][0]["receivers_count"]):
            # handle CTRL-C
            if _CTRL_EXIT_SIGNAL:
                return (err, samples_ir, samples_ir_window)

            ir_trid = configs[i]["setup"]["listeners"][0]["receivers"][ii]["track_id"]
            ir_folder = folders[i] + "/ir/"
            ir_yaml_filename = (
                configs[i]["custom"]["audio_filename"] + "_IR_rx_" + str(ii) + "_trid_" + str(ir_trid) + ".yaml"
            )

            ir_yaml_file = ir_folder + "/" + ir_yaml_filename

            ir_yaml = []

            try:
                with open(ir_yaml_file, "r") as file:
                    ir_yaml = yaml.safe_load(file)
            except:
                logger.error("ERROR while reading {}".format(ir_yaml_file))
                ir_yaml = None

            if ir_yaml != None:
                data[i, ii] = ir_yaml["ir_delay"]
                samples_ir = max(samples_ir, int(ir_yaml["ir_samples"]))
                samples_ir_window = max(samples_ir_window, int(ir_yaml["ir_norm_hipass_window_samples"]))

    return (err, samples_ir, samples_ir_window)


def read_ir_sample(params):
    global _CTRL_EXIT_SIGNAL

    err = 0

    # unpack manually
    i = params[0]
    config = params[1]
    folder = params[2]
    zero_delay = params[3]
    sofa_data_ir = params[4]

    for ii in range(config["setup"]["listeners"][0]["receivers_count"]):
        # handle CTRL-C
        if _CTRL_EXIT_SIGNAL:
            return

        ir_trid = config["setup"]["listeners"][0]["receivers"][ii]["track_id"]
        ir_folder = folder + "/ir/"
        ir_pyfar_filename = config["custom"]["audio_filename"] + "_IR_rx_" + str(ii) + "_trid_" + str(ir_trid) + ".far"
        ir_pyfar_file = ir_folder + "/" + ir_pyfar_filename

        logger.info(ir_pyfar_file)

        ir_pyfar = []

        try:
            # with open(ir_pyfar_file, "r") as file:
            ir_pyfar = pf.io.read(ir_pyfar_file)
        except:
            logger.error("ERROR while reading {}".format(ir_pyfar_file))
            ir_pyfar = None

        if ir_pyfar != None:
            # fetch impulse response in time domain
            if zero_delay == False:
                sofa_data_ir[i, ii, :] = ir_pyfar["ir_norm_hipass_window"].time[0]
            else:
                # retrieve info from file processing, 3DTune-In requires zero-delay aligned files!!
                ir_info = ir_pyfar["ir_info"]
                ir_delay_samples = int(ir_info[_IR_INFO_DELAY_SAMPLES])

                # make sure we preserve the peak for the final IR
                # ir_delay_samples = np.argmax(np.abs(ir_pyfar["ir_norm_hipass_window"].time[0]))
                # if ir_delay_samples > 4:
                #     ir_delay_samples -= 4

                # ir_delay_samples = compute_delay(ir_pyfar["ir_norm_hipass_window"].time[0])
                ir_delay_samples = compute_delay_adj(ir_pyfar["ir_norm_hipass_window"].time[0], ir_delay_samples)

                ir_len = ir_pyfar["ir_norm_hipass_window"].n_samples

                if ir_len > ir_delay_samples:
                    tmp = ir_len - ir_delay_samples
                    sofa_data_ir[i, ii, 0:tmp] = ir_pyfar["ir_norm_hipass_window"].time[0][ir_delay_samples:]
                else:
                    logger.error(
                        "ERROR: invalide delay samples for:{} rx_id:{} [{}<{}] ".format(
                            ir_pyfar_filename, ii, ir_len, ir_delay_samples
                        )
                    )


def read_ir_samples(data=None, configs=None, folders=None, zero_delay=False):
    global _CTRL_EXIT_SIGNAL

    err = 0

    for i in range(len(configs)):
        for ii in range(configs[i]["setup"]["listeners"][0]["receivers_count"]):
            # handle CTRL-C
            if _CTRL_EXIT_SIGNAL:
                return

            ir_trid = configs[i]["setup"]["listeners"][0]["receivers"][ii]["track_id"]
            ir_folder = folders[i] + "/ir/"
            ir_pyfar_filename = (
                configs[i]["custom"]["audio_filename"] + "_IR_rx_" + str(ii) + "_trid_" + str(ir_trid) + ".far"
            )
            ir_pyfar_file = ir_folder + "/" + ir_pyfar_filename

            logger.info(ir_pyfar_file)

            ir_pyfar = []

            try:
                # with open(ir_pyfar_file, "r") as file:
                ir_pyfar = pf.io.read(ir_pyfar_file)
            except:
                logger.error("ERROR while reading {}".format(ir_pyfar_file))
                ir_pyfar = None

            if ir_pyfar != None:
                # fetch impulse response in time domain

                if zero_delay == False:
                    data[i, ii, :] = ir_pyfar["ir_norm_hipass_window"].time[0]
                else:
                    # retrieve info from file processing, 3DTune-In requires zero-delay aligned files!!
                    ir_info = ir_pyfar["ir_info"]
                    ir_delay_samples = int(ir_info[_IR_INFO_DELAY_SAMPLES])

                    # make sure we preserve the peak for the final IR
                    # ir_delay_samples = np.argmax(np.abs(ir_pyfar["ir_norm_hipass_window"].time[0]))
                    # if ir_delay_samples > 4:
                    #     ir_delay_samples -= 4

                    # ir_delay_samples = compute_delay(ir_pyfar["ir_norm_hipass_window"].time[0])
                    ir_delay_samples = compute_delay_adj(ir_pyfar["ir_norm_hipass_window"].time[0], ir_delay_samples)

                    ir_len = ir_pyfar["ir_norm_hipass_window"].n_samples

                    if ir_len > ir_delay_samples:
                        tmp = ir_len - ir_delay_samples
                        data[i, ii, 0:tmp] = ir_pyfar["ir_norm_hipass_window"].time[0][ir_delay_samples:]
                    else:
                        logger.error(
                            "ERROR: invalide delay samples for:{} rx_id:{} [{}<{}] ".format(
                                ir_pyfar_filename, ii, ir_len, ir_delay_samples
                            )
                        )


def read_sources_listeners(data=None):
    """read audio config records and verify data correctness"""
    err = 0

    rv_listeners = []
    rv_sources = []
    rv_listeners_positions_count = 1
    rv_sources_positions_count = 1

    # data validation first
    for config in data:
        # check config syntax
        if (err == 0) and (config["syntax"]["name"] != "audio_measure"):
            log.error("compute_sofa: invalid config syntax")
            err += 1

        # AES69: mandate only one source
        if (err == 0) and (config["setup"]["sources_count"] != 1):
            log.error("compute_sofa: invalid sources count for {}".format(config["custom"]["audio_folder"]))
            err += 1

        # AES69: mandate only one listener
        if (err == 0) and (config["setup"]["listeners_count"] != 1):
            log.error("compute_sofa: invalid listeners count for {}".format(config["custom"]["audio_folder"]))
            err += 1

        # AES69: receivers count does not change between measures
        if (err == 0) and (
            config["setup"]["listeners"][0]["receivers_count"] != data[0]["setup"]["listeners"][0]["receivers_count"]
        ):
            log.error("compute_sofa: invalid listeners count for {}".format(config["custom"]["audio_folder"]))
            err += 1

        if err == 0:
            # AES69: receivers do not change specs and calibration between measures
            for idx in range(config["setup"]["listeners"][0]["receivers_count"]):
                receiver_ref = data[0]["setup"]["listeners"][0]["receivers"][idx]
                receiver_tmp = config["setup"]["listeners"][0]["receivers"][idx]
                if receiver_ref != receiver_tmp:
                    logger.error(
                        "compute_sofa: invalid receiver {} setup on listener for {}".format(
                            str(idx), config["custom"]["audio_folder"]
                        )
                    )
                    # logger.error(receiver_ref)
                    # logger.error(receiver_tmp)
                    err += 1

        # count listener positions, did the listener move or not?
        if (err == 0) and (config["setup"]["listeners"][0]["position"] != data[0]["setup"]["listeners"][0]["position"]):
            rv_listeners_positions_count += 1

        if err == 0:
            # AES69: emitters do not change specs and calibration between measures
            for idx in range(config["setup"]["sources"][0]["emitters_count"]):
                emitter_ref = data[0]["setup"]["sources"][0]["emitters"][idx]
                emitter_tmp = config["setup"]["sources"][0]["emitters"][idx]
                if emitter_ref != emitter_tmp:
                    logger.error(
                        "compute_sofa: invalid emitter {} setup on source for {}".format(
                            str(idx), config["custom"]["audio_folder"]
                        )
                    )
                    err += 1

        # count sources positions, did the listener move or not?
        if (err == 0) and (config["setup"]["sources"][0]["position"] != data[0]["setup"]["sources"][0]["position"]):
            rv_sources_positions_count += 1

    return err, rv_sources_positions_count, rv_listeners_positions_count


def compute_sofa(audio_recording=None, measures_list=None, yaml_params=None):
    if audio_recording == None:
        logger.error("compute_sofa: audio_recording is None")
        return

    if measures_list == None:
        logger.error("compute_sofa: measures_list is None")
        return

    if yaml_params == None:
        logger.error("compute_sofa: yaml_params is None")
        return

    measure_folder_list = []
    measure_audio_config_list = []
    measures_list = list(measures_list)

    # unpack list
    for m in measures_list:
        measure_folder_list.append(m[0])
        measure_audio_config_list.append(m[1])

    #
    # POOL: compute process pool size based on CPU/MEM requirements
    #
    mem_bytes = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")  # e.g. 4015976448
    mem_gib = mem_bytes / (1024.0**3)  # e.g. 3.74
    cpu_count = min([(os.cpu_count() - 2), yaml_params["cpu_process"]])
    cpu_count = max([_MIN_CPU_COUNT, cpu_count])
    if _PLOT_SAVE_GRAPH == 0:
        max_pool_size = min(cpu_count, int(mem_gib / _MIN_MEM_GB))
    else:
        max_pool_size = min(cpu_count, int(mem_gib / _MAX_MEM_GB))
    logger.info("Pool size: {}".format(max_pool_size))

    # ToDo: remove this print or move to logger!
    logger.info("-" * 80)
    logger.info("SOFA (S)patially (O)riented (F)ormat for (A)coustics:")
    logger.info("-" * 80)

    # list available conventions
    # sof.list_conventions()

    #
    # set the appropriate convention
    #

    # sofa convention: Free Field Head-related Impulse Response
    # sofa = sof.Sofa("SimpleFreeFieldHRIR")

    # sofa convention: Spatial Room Impulse Response
    sofa = sof.Sofa("SingleRoomSRIR", mandatory=False, verify=True)

    #
    # sofa convention: fill global section
    #

    # take the first to extract the global params
    measure_config_ref = measure_audio_config_list[0]

    # AES69-SOFA: General section
    sofa.GLOBAL_Title = measure_config_ref["general"]["title"]
    sofa.GLOBAL_ApplicationName = measure_config_ref["general"]["application_name"]
    sofa.GLOBAL_ApplicationVersion = str(measure_config_ref["general"]["application_version"])
    sofa.GLOBAL_AuthorContact = measure_config_ref["general"]["author"]["mail"]
    sofa.GLOBAL_Comment = measure_config_ref["general"]["comment"]
    sofa.GLOBAL_History = measure_config_ref["general"]["history"]
    sofa.GLOBAL_License = measure_config_ref["general"]["license"]
    sofa.GLOBAL_Organization = measure_config_ref["general"]["organization"]
    sofa.GLOBAL_References = measure_config_ref["general"]["references"]
    sofa.GLOBAL_Origin = measure_config_ref["general"]["origin"]
    sofa.GLOBAL_DateCreated = str(measure_config_ref["general"]["date_created"])
    sofa.GLOBAL_DateModified = str(measure_config_ref["general"]["date_modified"])
    sofa.GLOBAL_DatabaseName = measure_config_ref["general"]["database_name"]

    # AES69-SOFA: source/receiver details
    sofa.GLOBAL_ListenerShortName = measure_config_ref["setup"]["listeners"][0]["short_name"]
    sofa.GLOBAL_ListenerDescription = measure_config_ref["setup"]["listeners"][0]["description"]
    sofa.GLOBAL_SourceShortName = measure_config_ref["setup"]["sources"][0]["short_name"]
    sofa.GLOBAL_SourceDescription = measure_config_ref["setup"]["sources"][0]["description"]

    # AES69-SOFA: room definition
    sofa.GLOBAL_RoomType = measure_config_ref["room"]["type"]
    sofa.GLOBAL_RoomShortName = measure_config_ref["room"]["short_name"]
    sofa.GLOBAL_RoomDescription = measure_config_ref["room"]["description"]
    sofa.GLOBAL_RoomLocation = measure_config_ref["room"]["location"]
    sofa.GLOBAL_RoomGeometry = measure_config_ref["room"]["geometry"]
    sofa.RoomTemperature = measure_config_ref["room"]["temperature"]["value"]
    sofa.RoomTemperature_Units = measure_config_ref["room"]["temperature"]["units"]
    sofa.RoomVolume = measure_config_ref["room"]["volume"]["value"]
    sofa.RoomVolume_Units = measure_config_ref["room"]["volume"]["units"]
    sofa.RoomCorners = measure_config_ref["room"]["corners"]["numcorners"]
    sofa.RoomCorners_Type = measure_config_ref["room"]["corners"]["A"]["coord"]["type"]
    sofa.RoomCorners_Units = measure_config_ref["room"]["corners"]["A"]["coord"]["type"]
    sofa.RoomCornerA = measure_config_ref["room"]["corners"]["A"]["coord"]["value"]
    sofa.RoomCornerB = measure_config_ref["room"]["corners"]["B"]["coord"]["value"]

    # AES69-SOFA: Audio format
    sofa.Data_SamplingRate = measure_config_ref["custom"]["recording"]["samplerate"]
    sofa.Data_SamplingRate_Units = measure_config_ref["custom"]["recording"]["units"]

    # CUSTOM: add WILSON_PRJ specific keyword
    sofa.add_attribute("GLOBAL_AuralysPrjAPI", "auralys_prj")
    sofa.add_attribute("GLOBAL_AuralysPrjAPIName", measure_config_ref["syntax"]["name"])
    tmp = (
        str(measure_config_ref["syntax"]["version"]["major"])
        + "."
        + str(measure_config_ref["syntax"]["version"]["minor"])
        + "."
        + str(measure_config_ref["syntax"]["version"]["revision"])
    )
    sofa.add_attribute("GLOBAL_AuralysPrjAPIVersion", tmp)

    try:
        sofa.verify()
    except:
        log.error("compute sofa: failure to verify GLOBAL section.")

    #
    # READ SOURCE & LISTENERS:
    #

    # coordinates see: https://pyfar.readthedocs.io/en/stable/classes/pyfar.coordinates.html
    # azimuth, elevation, distance

    (err, sources_positions_count, listeners_positions_count) = read_sources_listeners(measure_audio_config_list)

    #
    # AUDIO LISTENERS:
    #
    if 0 == err:
        # position
        tmp = []
        for config in measure_audio_config_list:
            tmp.append(config["setup"]["listeners"][0]["position"]["coord"]["value"])
        sofa.ListenerPosition = np.asarray(tmp)
        sofa.ListenerPosition_Type = str(measure_config_ref["setup"]["listeners"][0]["position"]["coord"]["type"])
        sofa.ListenerPosition_Units = str(
            ",".join(measure_config_ref["setup"]["listeners"][0]["position"]["coord"]["units"])
        )

        # view/up
        tmp = []
        for config in measure_audio_config_list:
            tmp.append(config["setup"]["listeners"][0]["position"]["view_vect"]["value"])
        sofa.ListenerView = np.asarray(tmp)
        sofa.ListenerView_Type = str(measure_config_ref["setup"]["listeners"][0]["position"]["view_vect"]["type"])
        sofa.ListenerView_Units = str(
            ",".join(measure_config_ref["setup"]["listeners"][0]["position"]["view_vect"]["units"])
        )

        tmp = []
        for config in measure_audio_config_list:
            tmp.append(config["setup"]["listeners"][0]["position"]["up_vect"]["value"])
        sofa.ListenerUp = np.asarray(tmp)

    #
    # AUDIO RECEIVERS:
    #
    if 0 == err:
        # descriptions
        tmp = []
        for idx in range(measure_config_ref["setup"]["listeners"][0]["receivers_count"]):
            tmp_description = (
                measure_config_ref["setup"]["listeners"][0]["receivers"][idx]["short_name"]
                + " "
                + measure_config_ref["setup"]["listeners"][0]["receivers"][idx]["description"]
            )
            tmp.append(tmp_description)
        sofa.ReceiverDescriptions = np.asarray(tmp)

        # positions
        tmp = []
        for idx in range(measure_config_ref["setup"]["listeners"][0]["receivers_count"]):
            tmp.append(measure_config_ref["setup"]["listeners"][0]["receivers"][idx]["position"]["coord"]["value"])
        sofa.ReceiverPosition = np.asarray(tmp)
        sofa.ReceiverPosition_Type = str(
            measure_config_ref["setup"]["listeners"][0]["receivers"][idx]["position"]["coord"]["type"]
        )
        sofa.ReceiverPosition_Units = str(
            ",".join(measure_config_ref["setup"]["listeners"][0]["receivers"][idx]["position"]["coord"]["units"])
        )

        # view/up
        tmp = []
        for idx in range(measure_config_ref["setup"]["listeners"][0]["receivers_count"]):
            tmp.append(measure_config_ref["setup"]["listeners"][0]["receivers"][idx]["position"]["view_vect"]["value"])
        sofa.ReceiverView = np.asarray(tmp)
        sofa.ReceiverView_Type = str(
            measure_config_ref["setup"]["listeners"][0]["receivers"][idx]["position"]["view_vect"]["type"]
        )
        sofa.ReceiverView_Units = str(
            ",".join(measure_config_ref["setup"]["listeners"][0]["receivers"][idx]["position"]["view_vect"]["units"])
        )

        tmp = []
        for idx in range(measure_config_ref["setup"]["listeners"][0]["receivers_count"]):
            tmp.append(measure_config_ref["setup"]["listeners"][0]["receivers"][idx]["position"]["up_vect"]["value"])
        sofa.ReceiverUp = np.asarray(tmp)

    #
    # AUDIO SOURCES:
    #
    if 0 == err:
        tmp = []
        for config in measure_audio_config_list:
            tmp.append(config["setup"]["sources"][0]["position"]["coord"]["value"])
        sofa.SourcePosition = np.asarray(tmp)
        sofa.SourcePosition_Type = str(measure_config_ref["setup"]["sources"][0]["position"]["coord"]["type"])
        sofa.SourcePosition_Units = str(
            ",".join(measure_config_ref["setup"]["sources"][0]["position"]["coord"]["units"])
        )

        # view/up
        tmp = []
        for config in measure_audio_config_list:
            tmp.append(config["setup"]["sources"][0]["position"]["view_vect"]["value"])
        sofa.SourceView = np.asarray(tmp)
        sofa.SourceView_Type = str(measure_config_ref["setup"]["sources"][0]["position"]["view_vect"]["type"])
        sofa.SourceView_Units = str(
            ",".join(measure_config_ref["setup"]["sources"][0]["position"]["view_vect"]["units"])
        )

        tmp = []
        for config in measure_audio_config_list:
            tmp.append(config["setup"]["sources"][0]["position"]["up_vect"]["value"])
        sofa.SourceUp = np.asarray(tmp)

    #
    # AUDIO EMITTERS:
    #
    if 0 == err:
        # descriptions
        tmp = []
        for idx in range(measure_config_ref["setup"]["sources"][0]["emitters_count"]):
            tmp_description = (
                measure_config_ref["setup"]["sources"][0]["emitters"][idx]["short_name"]
                + " "
                + measure_config_ref["setup"]["sources"][0]["emitters"][idx]["description"]
            )
            tmp.append(tmp_description)
        sofa.EmitterDescriptions = np.asarray(tmp)

        # positions
        tmp = []
        for idx in range(measure_config_ref["setup"]["sources"][0]["emitters_count"]):
            tmp.append(measure_config_ref["setup"]["sources"][0]["emitters"][idx]["position"]["coord"]["value"])
        sofa.EmitterPosition = np.asarray(tmp)
        sofa.EmitterPosition_Type = str(
            measure_config_ref["setup"]["sources"][0]["emitters"][idx]["position"]["coord"]["type"]
        )
        sofa.EmitterPosition_Units = str(
            ",".join(measure_config_ref["setup"]["sources"][0]["emitters"][idx]["position"]["coord"]["units"])
        )

        # view/up
        tmp = []
        for idx in range(measure_config_ref["setup"]["sources"][0]["emitters_count"]):
            tmp.append(measure_config_ref["setup"]["sources"][0]["emitters"][idx]["position"]["view_vect"]["value"])
        sofa.EmitterView = np.asarray(tmp)
        sofa.EmitterView_Type = str(
            measure_config_ref["setup"]["sources"][0]["emitters"][idx]["position"]["view_vect"]["type"]
        )
        sofa.EmitterView_Units = str(
            ",".join(measure_config_ref["setup"]["sources"][0]["emitters"][idx]["position"]["view_vect"]["units"])
        )

        tmp = []
        for idx in range(measure_config_ref["setup"]["sources"][0]["emitters_count"]):
            tmp.append(measure_config_ref["setup"]["sources"][0]["emitters"][idx]["position"]["up_vect"]["value"])
        sofa.EmitterUp = np.asarray(tmp)

    #
    # AUDIO DATA:
    #
    if 0 == err:
        measures_M = int(len(measure_audio_config_list))
        receivers_R = int(measure_audio_config_list[0]["setup"]["listeners"][0]["receivers_count"])

        #
        # measures dates
        sofa.MeasurementDate = np.zeros(measures_M)
        for date in sofa.MeasurementDate:
            date = measure_config_ref["general"]["date_modified"]

        #
        # audio delay for each source position
        sofa.Data_Delay = np.zeros((measures_M, receivers_R))

        (err, samples_ir, samples_ir_window) = read_ir_delays(
            sofa.Data_Delay, measure_audio_config_list, measure_folder_list
        )

        # clear audio samples
        sofa.Data_IR = []

        if max_pool_size > 1:
            #
            # PARALLEL DATA LOAD (multiprocess)
            #
            logger.info("audio samples: parallel data load (multiprocessing)")

            sofa.Data_IR = np.zeros((measures_M, receivers_R, samples_ir_window))

            zero_delay = True
            if yaml_params["zero_delay"] == False:
                zero_delay = False

            cpu_pool_params = []
            for i in range(len(measure_audio_config_list)):
                cpu_pool_params.append(
                    (
                        i,
                        measure_audio_config_list[i],
                        measure_folder_list[i],
                        zero_delay,
                        sofa.Data_IR,
                    )
                )

            cpu_pool = multiprocessing.pool.ThreadPool(processes=max_pool_size)
            cpu_pool.map(read_ir_sample, cpu_pool_params)

            cpu_pool.close()
            cpu_pool.join()

        else:
            #
            # SERIAL DATA LOAD (single process)
            #

            # audio samples for each position
            sofa.Data_IR = np.zeros((measures_M, receivers_R, samples_ir_window))

            if yaml_params["zero_delay"] == False:
                read_ir_samples(
                    data=sofa.Data_IR, configs=measure_audio_config_list, folders=measure_folder_list, zero_delay=False
                )
            else:
                read_ir_samples(
                    data=sofa.Data_IR, configs=measure_audio_config_list, folders=measure_folder_list, zero_delay=True
                )

    #
    # WRITE OUTPUT FILE
    #

    if 0 == err:
        if not (_CTRL_EXIT_SIGNAL):
            sofa.inspect()
            sofa.verify()

            if 0 == err:
                filepath = measure_folder_list[0].split(measure_config_ref["custom"]["audio_folder"])[0]
                filename = measure_config_ref["custom"]["project_folder"] + ".sofa"

                try:
                    logger.info("compute sofa: file writing ....")
                    sof.write_sofa(os.path.join(filepath, filename), sofa)
                    logger.info("compute sofa: output file done: {}".format(filepath + "/" + filename))

                except:
                    err = -1
                    logger.error("compute sofa: error writing sofa file: {}".format(filepath + "/" + filename))
        else:
            err = -1
            print("exiting on user request, output sofa file skipped.\n")

    return err


#
###############################################################################
# MAIN
###############################################################################
#

if __name__ == "__main__":
    # install CTRL-C handles
    signal.signal(signal.SIGINT, signal_handler)

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
    # check if we just want to list devices and quit
    #
    if args1.list_folders:
        measure_folder_list = []
        measure_folder_list_subfolder_count = []
        measure_folder_list_subfolder_format = []
        # search for available config.yaml for audio measurement folders
        configs = glob.glob("**/config.yaml", recursive=True)
        # filter only valid folders
        for config in configs:
            if re.search("_xAngle/config.yaml", config):
                # load config file
                measure_config = {}
                try:
                    with open(config, "r") as file:
                        measure_config = yaml.safe_load(file)
                except:
                    measure_config = None

                if None != measure_config:
                    # check syntax
                    if measure_config["syntax"]["name"] == "audio_measure":
                        # search for IR folder within results
                        tmp = config.split("/")
                        tmp = config.split(tmp[-1])
                        if (os.path.exists(tmp[0] + "ir")) and (0 < len(glob.glob(tmp[0] + "ir/*.wav"))):
                            # split pattern
                            tmp = config.split("/")
                            tmp = config.split(tmp[-2])
                            if not (tmp[0] in measure_folder_list):
                                measure_folder_list.append(tmp[0])
                                measure_folder_list_subfolder_count.append(1)
                                measure_folder_list_subfolder_format.append(measure_config["custom"]["recording"])
                            measure_folder_list_subfolder_count[measure_folder_list.index(tmp[0])] += 1

        if len(measure_folder_list) > 0:
            print("listing available audio measure folders:")
            print("========================================")
            for i in range(len(measure_folder_list)):
                print(
                    measure_folder_list[i]
                    + ", "
                    + str(measure_folder_list_subfolder_count[i])
                    + ", "
                    + str(measure_folder_list_subfolder_format[i])
                )
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
            "--measure_folder",
            type=str,
            help="folder with audio sweep measure results",
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
            "-z",
            "--zero_delay",
            action="store_true",
            help="remove IR delay for 3D_TuneIn_Toolkit",
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
            "--measure_folder",
            type=str,
            default=None,
            help="folder with audio sweep measure results",
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
            default="skip",
            help="skip, save, show, show_and_save (default: %(default)s)",
        )
        parser.add_argument(
            "-z",
            "--zero_delay",
            action="store_true",
            default=False,
            help="remove IR delay for 3D_TuneIn_Toolkit",
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
    # sanity checks to validate input params
    #
    if yaml_params["measure_folder"] == None:
        sys.exit("\n[ERROR] missing measure folder.")

    # audio recording format
    audio_recording = None

    measure_folder_list = []
    measure_audio_config_list = []

    #
    # walk the given folder and search for proper results
    #
    if not (os.path.isdir(yaml_params["measure_folder"])):
        sys.exit("\n[ERROR] cannot open folder: {}".format(yaml_params["measure_folder"]))

    logger.info("searching config.yaml: {}".format(yaml_params["measure_folder"]))

    for f in os.walk(yaml_params["measure_folder"]):
        if os.path.exists(os.path.join(str(f[0]), "config.yaml")):
            audio_config = ""
            try:
                with open(os.path.join(str(f[0]), "config.yaml"), "r") as file:
                    audio_config = yaml.safe_load(file)
            except:
                sys.exit("\n[ERROR] cannot open/parse yaml config file: {}".format(kwargs["ess_yaml_config"]))

            error_cnt = 0

            # sanity check on consistent audio format
            if audio_recording == None:
                audio_recording = audio_config["custom"]["recording"]
            else:
                tmp = audio_config["custom"]["recording"]
                if (
                    (audio_recording["bit_depth"] != tmp["bit_depth"])
                    or (audio_recording["format"] != tmp["format"])
                    or (audio_recording["samplerate"] != tmp["samplerate"])
                    or (audio_recording["subformat"] != tmp["subformat"])
                    or (audio_recording["units"] != tmp["units"])
                ):
                    logger.error("inconsistent audio recording format on: {}".format(folder))
                    error_cnt = error_cnt + 1

            # add folder to the list of measures only if a valid config is found
            try:
                if not (audio_config["syntax"]["name"] == "audio_measure"):
                    error_cnt = error_cnt + 1
            except:
                error_cnt = error_cnt + 1

            if error_cnt == 0:
                # add folder to the list of measures only if impulse_response folder is present
                for rx in audio_config["setup"]["listeners"][0]["receivers"]:
                    # check for "far" file
                    ir_filename = (
                        "sweep_0_IR_rx_"
                        + str(rx)
                        + "_trid_"
                        + str(audio_config["setup"]["listeners"][0]["receivers"][rx]["track_id"])
                        + ".far"
                    )
                    if os.path.exists(os.path.join(str(f[0]), "ir", ir_filename)):
                        try:
                            if os.stat(os.path.join(str(f[0]), "ir", ir_filename)) == 0:
                                error_cnt = error_cnt + 1
                        except:
                            error_cnt = error_cnt + 1
                    else:
                        error_cnt = error_cnt + 1

                    # check for "wav" file
                    ir_filename = (
                        "sweep_0_IR_rx_"
                        + str(rx)
                        + "_trid_"
                        + str(audio_config["setup"]["listeners"][0]["receivers"][rx]["track_id"])
                        + ".wav"
                    )
                    if os.path.exists(os.path.join(str(f[0]), "ir", ir_filename)):
                        try:
                            if os.stat(os.path.join(str(f[0]), "ir", ir_filename)) == 0:
                                error_cnt = error_cnt + 1
                        except:
                            error_cnt = error_cnt + 1
                    else:
                        error_cnt = error_cnt + 1

            # if everything is there ... add folder to the compute list
            if error_cnt == 0:
                measure_folder_list.append(f[0])
                measure_audio_config_list.append(audio_config)

    #
    # create SOFA object and fetch impulses
    #
    if len(measure_folder_list) > 0:
        measures_list = zip(measure_folder_list, measure_audio_config_list)
        compute_sofa(audio_recording, measures_list, yaml_params)
