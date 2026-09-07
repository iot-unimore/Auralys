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
import ctypes
import copy

import matplotlib
import matplotlib.pyplot as plt
import matplotlib.mlab as mlab
import argparse
import sys

import numpy as np
import pyfar as pf
import soundfile as sf
import sofar as sof

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

_IR_CROP_GUARD_s = 0.0001


def crop_guard_samples(samplerate=96000, offset=_IR_CROP_GUARD_s):
    """Samples kept ahead of a detected onset when an IR is cropped.

    compute_hrir.find_ir_onset triggers at a fraction of the envelope peak, so a
    little of the rising edge still sits before the index it reports.

    must be a multiple of 2: int() has to be applied AFTER the halving,
    int(offset * sr) / 2 * 2 gives back an odd number (9.0 at 96 kHz).
    """
    return int(offset * samplerate / 2) * 2


def compute_delay_offset(data=None, idx=0, sr=96000, offset=0.0001):
    """Back the crop index off by a small guard.

    Cropping the IR exactly at the detected arrival would cut into the leading
    edge of the wavefront: compute_hrir.find_ir_onset triggers at a fraction of
    the envelope peak, so part of the rising edge still sits before that index.
    The guard keeps it.

    NOTE: idx is the ONSET, not the peak. Until the onset detector replaced
          np.argmax in compute_hrir this guard also had to span the whole
          onset-to-peak distance, which it never reliably did (measured at 3 to
          34 samples, against a 9 sample guard). It is now a guard only.
    """
    adata = abs(data)

    peak_idx = idx

    if peak_idx == 0:
        peak_idx = np.argmax(adata)

    offset_samples = crop_guard_samples(sr, offset)

    if offset_samples < peak_idx:
        peak_idx = peak_idx - offset_samples

    return int(peak_idx)

def excluded_receivers(config=None, exclude_names=None):
    """Receiver ids whose short_name was named on --exclude.

    Only affects which onsets are allowed to set the zero_delay time origin. A
    receiver that was never really recorded (an array left in the config from an
    older session) reports a meaningless early onset, and letting it win the
    minimum would delay every rendered track by the difference for nothing.
    """
    rv = []

    if not exclude_names:
        return rv

    known = []
    for idx in range(config["setup"]["listeners"][0]["receivers_count"]):
        short_name = config["setup"]["listeners"][0]["receivers"][idx].get("short_name")
        if short_name not in known:
            known.append(short_name)
        if short_name in exclude_names:
            rv.append(idx)

    for name in exclude_names:
        if name not in known:
            logger.warning(
                "compute sofa: --exclude '{}' matches no receiver, ignored (this listener has: {})".format(
                    name, ", ".join(str(k) for k in known)
                )
            )

    return rv


def scan_onset_minimum(configs=None, folders=None, exclude_list=None):
    """Earliest IR onset over every receiver of the session that is not excluded.

    This is the time origin the session is referenced to. It has to span the
    receivers that end up rendered TOGETHER, not just the ones this run writes:
    3DTune-In re-zeroes each file it loads against that file own smallest
    Data.Delay, so files that share a render have to agree on it. See the
    onset_reference block in compute_sofa().

    Reads the two lines it needs out of each sidecar instead of parsing them:
    yaml.safe_load over every receiver of every measure is a slow way to find two
    numbers, and this runs before any of the real work. ir_delay_samples is the
    integer crop index the minimum has to be expressed in; ir_delay is the same
    arrival with sub-sample precision, and the mean of it is what the render
    latency is built on, where flooring would cost half a sample.

    Returns (minimum in samples, mean arrival in seconds, onsets read, errors).
    """
    global _CTRL_EXIT_SIGNAL

    err = 0
    count = 0
    rv = None
    total = 0.0

    for i in range(len(configs)):
        # handle CTRL-C
        if _CTRL_EXIT_SIGNAL:
            return (rv, (total / count) if count else None, count, err)

        for ii in range(configs[i]["setup"]["listeners"][0]["receivers_count"]):
            if (exclude_list != None) and (ii in exclude_list):
                continue

            ir_trid = configs[i]["setup"]["listeners"][0]["receivers"][ii]["track_id"]
            ir_yaml_file = (
                folders[i]
                + "/ir/"
                + configs[i]["custom"]["audio_filename"]
                + "_IR_rx_"
                + str(ii)
                + "_trid_"
                + str(ir_trid)
                + ".yaml"
            )

            value = None
            arrival = None
            try:
                with open(ir_yaml_file, "r") as file:
                    for line in file:
                        if line.startswith("ir_delay_samples:"):
                            value = int(line.split(":", 1)[1].strip().strip("'\""))
                        elif line.startswith("ir_delay:"):
                            arrival = float(line.split(":", 1)[1].strip().strip("'\""))
                        if (value != None) and (arrival != None):
                            break
            except:
                value = None
                arrival = None

            if (value == None) or (arrival == None):
                # a missing onset here would silently raise the reference and skew
                # this file against the others: report it instead
                logger.error("compute sofa: cannot read onset from {}".format(ir_yaml_file))
                err += 1
            else:
                count += 1
                total += arrival
                if (rv == None) or (value < rv):
                    rv = value

    return (rv, (total / count) if count else None, count, err)


def sibling_reference_check(filepath=None, project=None, filename=None, reference=None):
    """Refuse to add a file to a session built on a different time origin.

    Each run works the reference out on its own, so a --exclude passed to some of
    them and not the others would go unnoticed and skew the merged tracks. Every
    file records what it used, so compare against the ones already on disk.
    """
    err = 0

    try:
        import netCDF4
    except:
        logger.warning(
            "compute sofa: netCDF4 not available, cannot cross check the zero_delay "
            "reference against the other files of this session"
        )
        return 0

    for f in sorted(glob.glob(os.path.join(filepath, project + "_*.sofa"))):
        if os.path.basename(f) == filename:
            continue

        other = None
        try:
            nc = netCDF4.Dataset(f, "r")
            # sofar stores GLOBAL_Foo as the plain netCDF attribute Foo
            if "AuralysPrjZeroDelayReference" in nc.ncattrs():
                other = int(nc.getncattr("AuralysPrjZeroDelayReference"))
            nc.close()
        except:
            other = None

        if other == None:
            logger.warning(
                "compute sofa: {} records no zero_delay reference, it predates this and will "
                "NOT stay aligned with the file being written".format(os.path.basename(f))
            )
        elif other != reference:
            logger.error(
                "compute sofa: {} was built on reference {}, this run is on {}: rendered together "
                "the two would be skewed by {} samples. rebuild the session with the same "
                "--exclude, or remove the stale file.".format(
                    os.path.basename(f), other, reference, abs(other - reference)
                )
            )
            err += 1

    return err


def read_ir_delays(data=None, data_onset=None, configs=None, folders=None, receivers_list=None):
    """Collect the per-measurement arrival times written by compute_hrir.

    data       : (M,R) filled with ir_delay_samples, the integer crop index
    data_onset : (M,R) filled with ir_delay, the sub-sample arrival in seconds
    """
    global _CTRL_EXIT_SIGNAL

    err = 0
    samples_ir = 0
    samples_ir_window = 0

    for i in range(len(configs)):
        selection_list = range(configs[i]["setup"]["listeners"][0]["receivers_count"])
        if receivers_list != None:
            selection_list = receivers_list

        idx = 0
        for ii in selection_list:  # range(configs[i]["setup"]["listeners"][0]["receivers_count"]):
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
                #
                # AES69-2022: Data.Delay is expressed in samples, 3DTuneIn is
                # following the spec. The sub-sample arrival is kept separately
                # in data_onset, in seconds, since Data.Delay cannot hold it.
                #
                rx_slot = idx if receivers_list != None else ii

                data[i, rx_slot] = int(ir_yaml["ir_delay_samples"])
                if data_onset is not None:
                    data_onset[i, rx_slot] = float(ir_yaml["ir_delay"])

                samples_ir = max(samples_ir, int(ir_yaml["ir_samples"]))
                samples_ir_window = max(samples_ir_window, int(ir_yaml["ir_norm_hipass_window_samples"]))
            else:
                # leaving the slot at zero would put a silently wrong delay in the
                # SOFA file and still exit clean: report it instead
                err += 1

            idx += 1

    return (err, samples_ir, samples_ir_window)


def read_ir_sample(params):
    """Load one measurement into the shared SOFA arrays. Returns an error count.

    NOTE: the caller runs this through a ThreadPool, NOT a process Pool. The
          writes into sofa_data_ir / sofa_data_delay are in-place on shared
          memory: with a process Pool every write would land in a forked copy
          and the SOFA file would come out all zeros.
    """
    global _CTRL_EXIT_SIGNAL

    err = 0

    # unpack manually
    i = params[0]
    config = params[1]
    folder = params[2]
    receivers_list = params[3]
    zero_delay = params[4]
    samples_ir_window = params[5]
    sofa_data_ir = params[6]
    sofa_data_delay = params[7]
    remove_direct_path = params[8]
    crop_offset = params[9]

    selection_list = range(config["setup"]["listeners"][0]["receivers_count"])
    if receivers_list != None:
        selection_list = receivers_list

    idx = 0
    for ii in selection_list:  # range(configs[i]["setup"]["listeners"][0]["receivers_count"]):
        # handle CTRL-C
        if _CTRL_EXIT_SIGNAL:
            return err

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
            # an unreadable measurement leaves this direction all zeros in the
            # SOFA file: report it instead of writing a silent hole
            err += 1

        if ir_pyfar != None:
            # fetch impulse response in time domain
            if zero_delay == False:
                if receivers_list != None:
                    sofa_data_ir[i, idx, :] = ir_pyfar["ir_norm_hipass_window"].time[0][0:samples_ir_window]
                else:
                    sofa_data_ir[i, ii, :] = ir_pyfar["ir_norm_hipass_window"].time[0][0:samples_ir_window]

            else:
                # retrieve info from file processing, 3DTune-In requires zero-delay aligned files!!
                ir_info = ir_pyfar["ir_info"]
                ir_delay_samples = int(ir_info[_IR_INFO_DELAY_SAMPLES])
                ir_samplerate = int(ir_info[_IR_INFO_SAMPLERATE])
                ir_samples = len(ir_pyfar["ir_norm_hipass_window"].time[0])

                # ir_delay_samples = compute_delay_adj(ir_pyfar["ir_norm_hipass_window"].time[0], ir_delay_samples)
                # crop_offset is this file own first arrival measured from the session
                # time origin, so every file of the session lands on the same origin and
                # min(Data.Delay) comes out equal in all of them. see the zero_delay block
                # in compute_sofa(): that equality is what keeps the receiver pairs aligned
                # when they are rendered separately and merged.
                ir_delay_samples = ir_delay_samples - crop_offset
                ir_len = ir_pyfar["ir_norm_hipass_window"].n_samples

                if (ir_delay_samples >= 0) and (ir_len > ir_delay_samples):
                    # window/all samples count
                    tmp = ir_len - ir_delay_samples
                    if tmp > samples_ir_window:
                        tmp = samples_ir_window

                    if(remove_direct_path>0):
                        # TODO: apply windowing to the crossing point
                        # measured from the onset, as before, not from the crop index
                        ir_guarded_samples = compute_delay_offset(
                            data=ir_pyfar["ir_norm_hipass_window"].time[0],
                            idx=(ir_delay_samples + crop_offset),
                            sr=ir_samplerate,
                            offset=0.0001,
                        )
                        ir_null_samples = ir_guarded_samples + int(round(ir_samplerate*remove_direct_path))
                        if(ir_samples < ir_null_samples):
                            ir_null_samples = ir_samples
                        # erase direct path wave
                        ir_pyfar["ir_norm_hipass_window"].time[0][0:ir_null_samples] = np.zeros(ir_null_samples)

                    if receivers_list != None:
                        sofa_data_ir[i, idx, 0:tmp] = ir_pyfar["ir_norm_hipass_window"].time[0][
                            ir_delay_samples : (ir_delay_samples + tmp)
                        ]

                        sofa_data_delay[i, idx] = ir_delay_samples                        
                    else:
                        sofa_data_ir[i, ii, 0:tmp] = ir_pyfar["ir_norm_hipass_window"].time[0][
                            ir_delay_samples : (ir_delay_samples + tmp)
                        ]

                        sofa_data_delay[i, ii] = ir_delay_samples
                else:
                    logger.error(
                        "ERROR: invalid crop index for:{} rx_id:{} [crop {} outside 0..{}] ".format(
                            ir_pyfar_filename, ii, ir_delay_samples, ir_len
                        )
                    )
                    err += 1

        idx += 1

    return err


def read_ir_samples(data=None, data_delay=None, configs=None, folders=None, zero_delay=False, receivers_list=None, samples_ir_window=0, remove_direct_path=0.0, crop_offset=0):
    global _CTRL_EXIT_SIGNAL

    err = 0

    for i in range(len(configs)):
        selection_list = range(configs[i]["setup"]["listeners"][0]["receivers_count"])
        if receivers_list != None:
            selection_list = receivers_list

        idx = 0
        for ii in selection_list:  # range(configs[i]["setup"]["listeners"][0]["receivers_count"]):
            # handle CTRL-C
            if _CTRL_EXIT_SIGNAL:
                return err

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
                # an unreadable measurement leaves this direction all zeros in the
                # SOFA file: report it instead of writing a silent hole
                err += 1

            if ir_pyfar != None:
                # fetch impulse response in time domain
                if zero_delay == False:
                    if receivers_list != None:
                        data[i, idx, :] = ir_pyfar["ir_norm_hipass_window"].time[0][0:samples_ir_window]
                    else:
                        data[i, ii, :] = ir_pyfar["ir_norm_hipass_window"].time[0][0:samples_ir_window]

                else:
                    # retrieve info from file processing, 3DTune-In requires zero-delay aligned files!!
                    ir_info = ir_pyfar["ir_info"]
                    ir_delay_samples = int(ir_info[_IR_INFO_DELAY_SAMPLES])
                    ir_samplerate = int(ir_info[_IR_INFO_SAMPLERATE])
                    ir_samples = len(ir_pyfar["ir_norm_hipass_window"].time[0])

                    # ir_delay_samples = compute_delay(ir_pyfar["ir_norm_hipass_window"].time[0])
                    # ir_delay_samples = compute_delay_adj(ir_pyfar["ir_norm_hipass_window"].time[0], ir_delay_samples)
                    # crop_offset is this file own first arrival measured from the session
                    # time origin, so every file of the session lands on the same origin and
                    # min(Data.Delay) comes out equal in all of them. see the zero_delay block
                    # in compute_sofa(): that equality is what keeps the receiver pairs aligned
                    # when they are rendered separately and merged.
                    ir_delay_samples = ir_delay_samples - crop_offset

                    ir_len = ir_pyfar["ir_norm_hipass_window"].n_samples

                    if (ir_delay_samples >= 0) and (ir_len > ir_delay_samples):
                        # window/all samples count
                        tmp = ir_len - ir_delay_samples
                        if tmp > samples_ir_window:
                            tmp = samples_ir_window

                        if(remove_direct_path>0):
                            # TODO: apply windowing to the crossing point
                            # measured from the onset, as before, not from the crop index
                            ir_guarded_samples = compute_delay_offset(
                                data=ir_pyfar["ir_norm_hipass_window"].time[0],
                                idx=(ir_delay_samples + crop_offset),
                                sr=ir_samplerate,
                                offset=0.0001,
                            )
                            ir_null_samples = ir_guarded_samples + int(round(ir_samplerate*remove_direct_path))
                            if(ir_samples < ir_null_samples):
                                ir_null_samples = ir_samples
                            # erase direct path wave
                            ir_pyfar["ir_norm_hipass_window"].time[0][0:ir_null_samples] = np.zeros(ir_null_samples)


                        if receivers_list != None:
                            data[i, idx, 0:tmp] = ir_pyfar["ir_norm_hipass_window"].time[0][
                                ir_delay_samples : (ir_delay_samples + tmp)
                            ]

                            data_delay[i, idx] = ir_delay_samples
                        else:
                            data[i, ii, 0:tmp] = ir_pyfar["ir_norm_hipass_window"].time[0][
                                ir_delay_samples : (ir_delay_samples + tmp)
                            ]

                            data_delay[i, ii] = ir_delay_samples                            
                    else:
                        logger.error(
                            "ERROR: invalid crop index for:{} rx_id:{} [crop {} outside 0..{}] ".format(
                                ir_pyfar_filename, ii, ir_delay_samples, ir_len
                            )
                        )
                        err += 1

            idx += 1

    return err


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
            logger.error("compute_sofa: invalid config syntax")
            err += 1

        # AES69: mandate only one source
        if (err == 0) and (config["setup"]["sources_count"] != 1):
            logger.error("compute_sofa: invalid sources count for {}".format(config["custom"]["audio_folder"]))
            err += 1

        # AES69: mandate only one listener
        if (err == 0) and (config["setup"]["listeners_count"] != 1):
            logger.error("compute_sofa: invalid listeners count for {}".format(config["custom"]["audio_folder"]))
            err += 1

        # AES69: receivers count does not change between measures
        if (err == 0) and (
            config["setup"]["listeners"][0]["receivers_count"] != data[0]["setup"]["listeners"][0]["receivers_count"]
        ):
            logger.error("compute_sofa: invalid listeners count for {}".format(config["custom"]["audio_folder"]))
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

        # filter receivers if needed
        rv_receiver_selection = []
        if err == 0:
            if yaml_params["select_rx"] != None:
                for idx in range(config["setup"]["listeners"][0]["receivers_count"]):
                    receiver_tmp = config["setup"]["listeners"][0]["receivers"][idx]

                    key = yaml_params["select_rx"].split(",")
                    if len(key) == 1:
                        key.append(None)

                    if receiver_tmp["short_name"] == key[0]:
                        if key[1] == None:
                            if idx not in rv_receiver_selection:
                                rv_receiver_selection.append(idx)
                        else:
                            if key[1] in receiver_tmp["description"]:
                                if idx not in rv_receiver_selection:
                                    rv_receiver_selection.append(idx)

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

    return err, rv_sources_positions_count, rv_listeners_positions_count, rv_receiver_selection


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

    # time origin this file is referenced to, see the zero_delay block below
    onset_reference = 0

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
    sofa_convention = None

    if yaml_params["select_rx"] == None:
        # sofa convention: Spatial Room Impulse Response
        sofa = sof.Sofa("SingleRoomSRIR", mandatory=False, verify=True)
        sofa_convention = "SingleRoomSRIR"
    else:
        # sofa convention: Free Field Head-related Impulse Response
        sofa = sof.Sofa("SimpleFreeFieldHRIR", mandatory=False, verify=True)
        sofa_convention = "SimpleFreeFieldHRIR"
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
    if sofa_convention == "SingleRoomSRIR":
        sofa.GLOBAL_ListenerDescription = measure_config_ref["setup"]["listeners"][0]["description"]
        sofa.GLOBAL_SourceShortName = measure_config_ref["setup"]["sources"][0]["short_name"]
        sofa.GLOBAL_SourceDescription = measure_config_ref["setup"]["sources"][0]["description"]

    # AES69-SOFA: room definition
    sofa.GLOBAL_RoomType = measure_config_ref["room"]["type"]
    if sofa_convention == "SingleRoomSRIR":
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
        logger.error("compute sofa: failure to verify GLOBAL section.")

    #
    # READ SOURCE & LISTENERS:
    #

    # coordinates see: https://pyfar.readthedocs.io/en/stable/classes/pyfar.coordinates.html
    # azimuth, elevation, distance

    (err, sources_positions_count, listeners_positions_count, receivers_selection) = read_sources_listeners(
        measure_audio_config_list
    )

    #
    # AUDIO LISTENERS:
    #
    if 0 == err:
        # position
        tmp = []
        if listeners_positions_count == 1:
            tmp = measure_audio_config_list[0]["setup"]["listeners"][0]["position"]["coord"]["value"]
        else:
            for config in measure_audio_config_list:
                tmp.append(config["setup"]["listeners"][0]["position"]["coord"]["value"])
        sofa.ListenerPosition = np.asarray(tmp)
        sofa.ListenerPosition_Type = str(measure_config_ref["setup"]["listeners"][0]["position"]["coord"]["type"])
        sofa.ListenerPosition_Units = str(
            ",".join(measure_config_ref["setup"]["listeners"][0]["position"]["coord"]["units"])
        )

        # view/up
        tmp = []
        if listeners_positions_count == 1:
            tmp.append(measure_audio_config_list[0]["setup"]["listeners"][0]["position"]["view_vect"]["value"])
        else:
            for config in measure_audio_config_list:
                tmp.append(config["setup"]["listeners"][0]["position"]["view_vect"]["value"])
        sofa.ListenerView = np.asarray(tmp)
        sofa.ListenerView_Type = str(measure_config_ref["setup"]["listeners"][0]["position"]["view_vect"]["type"])
        sofa.ListenerView_Units = str(
            ",".join(measure_config_ref["setup"]["listeners"][0]["position"]["view_vect"]["units"])
        )

        tmp = []
        if listeners_positions_count == 1:
            tmp.append(measure_audio_config_list[0]["setup"]["listeners"][0]["position"]["up_vect"]["value"])
        else:
            for config in measure_audio_config_list:
                tmp.append(config["setup"]["listeners"][0]["position"]["up_vect"]["value"])
        sofa.ListenerUp = np.asarray(tmp)

    #
    # AUDIO RECEIVERS:
    #

    receivers_list = range(measure_config_ref["setup"]["listeners"][0]["receivers_count"])
    if len(receivers_selection) > 0:
        receivers_list = receivers_selection

    if 0 == err:
        # descriptions
        tmp = []
        if sofa_convention == "SingleRoomSRIR":
            for idx in receivers_list:  # range(measure_config_ref["setup"]["listeners"][0]["receivers_count"]):
                tmp_description = (
                    measure_config_ref["setup"]["listeners"][0]["receivers"][idx]["short_name"]
                    + " "
                    + measure_config_ref["setup"]["listeners"][0]["receivers"][idx]["description"]
                )
                tmp.append(tmp_description)
            sofa.ReceiverDescriptions = np.asarray(tmp)

        # positions
        tmp = []
        for idx in receivers_list:  # range(measure_config_ref["setup"]["listeners"][0]["receivers_count"]):
            tmp.append(measure_config_ref["setup"]["listeners"][0]["receivers"][idx]["position"]["coord"]["value"])
        sofa.ReceiverPosition = np.asarray(tmp)
        sofa.ReceiverPosition_Type = str(
            measure_config_ref["setup"]["listeners"][0]["receivers"][idx]["position"]["coord"]["type"]
        )
        sofa.ReceiverPosition_Units = str(
            ",".join(measure_config_ref["setup"]["listeners"][0]["receivers"][idx]["position"]["coord"]["units"])
        )

        # view/up
        if sofa_convention == "SingleRoomSRIR":
            tmp = []
            for idx in receivers_list:  # range(measure_config_ref["setup"]["listeners"][0]["receivers_count"]):
                tmp.append(
                    measure_config_ref["setup"]["listeners"][0]["receivers"][idx]["position"]["view_vect"]["value"]
                )
            sofa.ReceiverView = np.asarray(tmp)
            sofa.ReceiverView_Type = str(
                measure_config_ref["setup"]["listeners"][0]["receivers"][idx]["position"]["view_vect"]["type"]
            )
            sofa.ReceiverView_Units = str(
                ",".join(
                    measure_config_ref["setup"]["listeners"][0]["receivers"][idx]["position"]["view_vect"]["units"]
                )
            )

            tmp = []
            for idx in receivers_list:  # range(measure_config_ref["setup"]["listeners"][0]["receivers_count"]):
                tmp.append(
                    measure_config_ref["setup"]["listeners"][0]["receivers"][idx]["position"]["up_vect"]["value"]
                )
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
        if sofa_convention == "SingleRoomSRIR":
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
        if sofa_convention == "SingleRoomSRIR":
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
        receivers_R = int(
            len(receivers_list)
        )  # int(measure_audio_config_list[0]["setup"]["listeners"][0]["receivers_count"])

        #
        # measures dates
        if sofa_convention == "SingleRoomSRIR":
            sofa.MeasurementDate = np.zeros(measures_M)
            for date in sofa.MeasurementDate:
                date = measure_config_ref["general"]["date_modified"]

        #
        # audio delay for each source position
        sofa.Data_Delay = np.zeros((measures_M, receivers_R))

        AuralysPrjIROnsetDelay = np.zeros((measures_M, receivers_R))

        (err, samples_ir, samples_ir_window) = read_ir_delays(
            data=sofa.Data_Delay,
            data_onset=AuralysPrjIROnsetDelay,
            configs=measure_audio_config_list,
            folders=measure_folder_list,
            receivers_list=receivers_list,
        )

        if err:
            logger.error("compute sofa: {} IR delay entries could not be read, aborting.".format(err))

        #
        # zero_delay time origin.
        #
        # 3DTune-In re-zeroes every SOFA it loads against the smallest Data.Delay in
        # (HRTF.cpp, RemoveCommonDelay_HRTFDataBaseTable), so the arrival a
        # renderer ends up with is always "onset - min(Data.Delay) of this file".
        #
        # the origin has to be one value for the whole session, and as LARGE as it can
        # be: whatever is left in the HRIR after it is removed gets added on top of the
        # propagation delay the renderer computes for the virtual source, so anything
        # beyond the mic offset from the array centre is latency the recorded scene
        # never had. the largest admissible value is the earliest onset of any receiver
        # rendered alongside this one, because the arrival left behind can never go
        # negative: Data.Delay is unsigned and the impulse has to sit inside the stored
        # waveform. that is what scan_onset_minimum() looks for, less the crop guard so
        # the rising edge survives exactly as it always did.
        #
        # the scan deliberately covers receivers this run does not write, which is why
        # it walks the whole listener instead of receivers_list, and why --exclude
        # exists: an array left in the config from an older session still reports an
        # onset, and letting it win the minimum delays every rendered track for nothing.
        #
        crop_offset = 0
        exclude_list = []

        if (0 == err) and (yaml_params["zero_delay"] != False):
            exclude_list = excluded_receivers(config=measure_config_ref, exclude_names=yaml_params["exclude"])

            # the origin has to sit at or below every onset of the receivers we write,
            # or their crop would run past the arrival. excluding one of them would do
            # exactly that, so refuse instead of quietly clamping
            clash = [rx for rx in receivers_list if rx in exclude_list]
            if len(clash) > 0:
                logger.error(
                    "compute sofa: --exclude covers receiver(s) {} that this run writes".format(
                        ", ".join(str(rx) for rx in clash)
                    )
                )
                err += 1

        if (0 == err) and (yaml_params["zero_delay"] != False):
            (scan_minimum, scan_mean, scan_count, scan_err) = scan_onset_minimum(
                configs=measure_audio_config_list,
                folders=measure_folder_list,
                exclude_list=exclude_list,
            )

            if (scan_err > 0) or (scan_minimum == None) or (scan_mean == None):
                logger.error(
                    "compute sofa: {} onset(s) unreadable while looking for the zero_delay "
                    "origin, aborting.".format(scan_err)
                )
                err += 1
            else:
                onset_reference = scan_minimum - crop_guard_samples(int(sofa.Data_SamplingRate))
                crop_offset = int(sofa.Data_Delay.min()) - onset_reference

                logger.info(
                    "compute sofa: zero_delay origin {} samples ({:.3f} ms), earliest of {} "
                    "onsets{}".format(
                        onset_reference,
                        1000.0 * onset_reference / float(sofa.Data_SamplingRate),
                        scan_count,
                        ""
                        if len(exclude_list) == 0
                        else ", excluding rx " + ", ".join(str(rx) for rx in exclude_list),
                    )
                )
                logger.info(
                    "compute sofa: this file crops {} samples ahead of each onset, "
                    "min(Data.Delay) will be {}".format(crop_offset, onset_reference)
                )

                #
                # latency the render is left carrying, on top of the propagation delay
                # the renderer computes for the virtual source.
                #
                # 3DTune-In renders as "distance to the listener origin over c" plus
                # whatever delay the HRIR still holds, so the HRIR has to supply each
                # receiver offset from that origin. that offset is SIGNED: a receiver on
                # the source side of the array should arrive before the origin does. a
                # SOFA cannot say that, Data.Delay is unsigned and the impulse has to sit
                # inside the stored waveform, so the whole set is lifted until the most
                # negative case reaches zero. what is left over is this.
                #
                # it comes out as the mean arrival minus the origin because, averaged
                # over a full azimuth circle with elevations symmetric about zero, the
                # receiver offset averages to zero and only the lift survives. that also
                # makes it derivable from the file alone, as
                # mean(AuralysPrjIROnsetDelay) * fs - min(Data.Delay), but it is written
                # down so a reader does not have to know the trick, and computed over the
                # same receivers as the origin so every file of the session carries the
                # SAME number. trimming different amounts off different tracks would put
                # back exactly the skew the shared origin removes.
                #
                #
                render_latency = scan_mean - (onset_reference / float(sofa.Data_SamplingRate))
                logger.info(
                    "compute sofa: render latency {:.1f} us ({:.2f} samples), trim this from "
                    "every rendered track to land on free field timing".format(
                        render_latency * 1e6, render_latency * float(sofa.Data_SamplingRate)
                    )
                )

                sofa.add_attribute("GLOBAL_AuralysPrjRenderLatency", "{:.9f}".format(render_latency))
                sofa.add_attribute(
                    "GLOBAL_AuralysPrjRenderLatencyDescription",
                    "seconds of latency left in the render on top of the propagation delay "
                    "the renderer applies for the virtual source, caused by a SOFA not being "
                    "able to hold the negative half of a receiver offset from the array "
                    "origin. trim it from the front of every rendered track to bring absolute "
                    "arrivals onto free field timing. it is identical in every SOFA file of "
                    "this session and must be applied equally to all of them: different values "
                    "on different tracks would skew them against each other. what is left "
                    "after trimming is the spread of the measured source arc radius over "
                    "elevation, which no constant can remove.",
                )

                #
                # record the origin. it stays derivable from the file, but only while
                # AuralysPrjIROnsetDelay survives in it, and sibling_reference_check()
                # needs it written down to be able to compare one file against another.
                #
                sofa.add_attribute("GLOBAL_AuralysPrjZeroDelayReference", str(onset_reference))
                sofa.add_attribute(
                    "GLOBAL_AuralysPrjZeroDelayReferenceDescription",
                    "time origin of this file, in samples from the start of the raw impulse "
                    "response. a renderer that removes the smallest Data.Delay of the file "
                    "(3DTune-In does) reconstructs every arrival as its onset minus this "
                    "value. all the SOFA files of a session that are rendered together have "
                    "to carry the same number or their tracks will be skewed against each other.",
                )

        #
        # we always keep the measured time of arrival as a private param.
        #
        # this is NOT a duplicate of Data.Delay: AES69 expresses Data.Delay in
        # whole samples and it holds the index the IR was actually cropped at
        # (arrival minus crop_offset), while this one is the sub-sample arrival
        # in seconds as measured by compute_hrir.find_ir_onset.
        #
        # it used to be called IRPeakDelay, which described np.argmax of the IR.
        # compute_hrir now reports the onset, so the name would be misleading.
        if 0 == err:
            sofa.add_variable("AuralysPrjIROnsetDelay", AuralysPrjIROnsetDelay, dtype="double", dimensions="MR")
            sofa.add_attribute("AuralysPrjIROnsetDelay_Units", "seconds")
            sofa.add_attribute(
                "AuralysPrjIROnsetDelay_Description",
                "time of arrival of the direct sound, sub-sample precision, "
                "referenced to the start of the raw impulse response",
            )

        #
        # if we are not loading IR as "zero-delay" reference we have to
        # put to zero the Data_Delay or we will introduce a double delay/
        # when doing the sofa rendering
        if yaml_params["zero_delay"] == False:
            sofa.Data_Delay = np.zeros((measures_M, receivers_R))

        #
        # audio samples for each position
        if yaml_params["ir_window"] > 0:
            # compute how many samples to fetch, make it even
            tmp = (int(yaml_params["ir_window"] * sofa.Data_SamplingRate / 2)) * 2
            if tmp < samples_ir_window:
                samples_ir_window = tmp
                logger.info(
                    "ir_window {}ms, using ir_window {} samples".format(yaml_params["ir_window"], samples_ir_window)
                )

        # clear audio samples
        sofa.Data_IR = []

        if max_pool_size > 1:
            #
            # PARALLEL DATA LOAD (multiprocess)
            #
            logger.info("audio samples: parallel data load (multiprocessing)")

            # sofa.Data_IR = shared_array(dtype=np.float64, shape=(measures_M, receivers_R, samples_ir_window))

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
                        receivers_list,
                        zero_delay,
                        samples_ir_window,
                        sofa.Data_IR,
                        sofa.Data_Delay,
                        float(yaml_params["remove_direct_path"]),
                        crop_offset,
                    )
                )

            cpu_pool = multiprocessing.pool.ThreadPool(processes=max_pool_size)
            pool_errors = cpu_pool.map(read_ir_sample, cpu_pool_params)

            cpu_pool.close()
            cpu_pool.join()

            err += sum(e for e in pool_errors if e)

        else:
            #
            # SERIAL DATA LOAD (single process)
            #
            logger.info("audio samples: serial data load (single process)")

            sofa.Data_IR = np.zeros((measures_M, receivers_R, samples_ir_window))

            err += read_ir_samples(
                data=sofa.Data_IR,
                data_delay=sofa.Data_Delay,
                configs=measure_audio_config_list,
                folders=measure_folder_list,
                zero_delay=bool(yaml_params["zero_delay"]),
                receivers_list=receivers_list,
                samples_ir_window=samples_ir_window,
                remove_direct_path=float(yaml_params["remove_direct_path"]),
                crop_offset=crop_offset,
            )

        if (0 == err) and (yaml_params["zero_delay"] != False):
            # the invariant the separately rendered pairs depend on: every file of the
            # session has to bottom out on the same Data.Delay, or they will not share
            # a time origin once they are merged
            data_delay_min = int(sofa.Data_Delay.min())
            if onset_reference != data_delay_min:
                logger.error(
                    "compute sofa: min(Data.Delay) is {}, expected {}. this file would not "
                    "stay time aligned with the other receiver pairs.".format(
                        data_delay_min, onset_reference
                    )
                )
                err += 1
            else:
                logger.info(
                    "compute sofa: min(Data.Delay) is {}, the session time origin".format(onset_reference)
                )

        if err:
            # a missing or unreadable measurement leaves an all-zero HRIR at that
            # direction. the file would still pass sofa.verify(), so refuse to
            # write it rather than hand out a SOFA with silent holes.
            logger.error("compute sofa: {} measurement(s) failed to load, output file skipped.".format(err))

    #
    # WRITE OUTPUT FILE
    #

    if 0 == err:
        if not (_CTRL_EXIT_SIGNAL):
            sofa.inspect()
            sofa.verify()

            fileappend = ""
            if yaml_params["select_rx"] != None:
                fileappend = yaml_params["select_rx"].replace(",", "_")

            filepath = measure_folder_list[0].split(measure_config_ref["custom"]["audio_folder"])[0]
            filename = measure_config_ref["custom"]["project_folder"] + "_" + fileappend + ".sofa"

            #
            # the files of a session are rendered separately and merged, so they only
            # stay aligned if they were built on the same origin. each run works that
            # out on its own, so check against what is already on disk before adding
            # another file to the set.
            #
            if yaml_params["zero_delay"] != False:
                err += sibling_reference_check(
                    filepath=filepath,
                    project=measure_config_ref["custom"]["project_folder"],
                    filename=filename,
                    reference=onset_reference,
                )

            if 0 == err:
                try:
                    logger.info("compute sofa: file writing: {} ...".format(filename))
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
        parser.add_argument(
            "-r",
            "--remove_direct_path",
            type=float,
            help="remove direct_path for 3D_TuneIn_Toolkit",
        )
        parser.add_argument(
            "-irw",
            "--ir_window",
            type=float,
            help="window (ms) to cut IR (default: %(default)s)",
        )
        parser.add_argument(
            "-s",
            "--select_rx",
            type=str,
            help="select receivers array",
        )
        parser.add_argument(
            "-x",
            "--exclude",
            type=str,
            nargs="+",
            help="receiver short_name(s) kept out of the zero_delay time reference",
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
            help="remove IR delay for 3D_TuneIn_Toolkit (default: %(default)s)",
        )
        parser.add_argument(
            "-r",
            "--remove_direct_path",
            type=float,
            default=0.0,
            help="remove direct_path for 3D_TuneIn_Toolkit (default: %(default)s) s",
        )
        parser.add_argument(
            "-irw",
            "--ir_window",
            default=0,
            type=float,
            help="window (ms) to cut IR (default: %(default)s)",
        )
        parser.add_argument(
            "-s",
            "--select_rx",
            type=str,
            default="array_six,middle",
            help="select receiver array (default: %(default)s)",
        )
        parser.add_argument(
            "-x",
            "--exclude",
            type=str,
            nargs="+",
            default=None,
            help="receiver short_name(s) kept out of the zero_delay time reference "
            "(default: %(default)s, every receiver of the listener counts)",
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

    #
    # remove_direct_path must to be used with zero_delay
    #
    if ( yaml_params["zero_delay"] == False ) and ( yaml_params["remove_direct_path"] > 0.0 ):
        logger.info("BRIR computation with direct path removal requires zero_delay. enabling zero_delay option.")
        yaml_params["zero_delay"] = True

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

    measure_folder_skipped = []

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
                            # os.stat() returns a stat_result, it is never == 0:
                            # the empty-file check never fired, use st_size
                            if os.stat(os.path.join(str(f[0]), "ir", ir_filename)).st_size == 0:
                                logger.error("empty IR file: {}".format(os.path.join(str(f[0]), "ir", ir_filename)))
                                error_cnt = error_cnt + 1
                        except:
                            logger.error("cannot stat IR file: {}".format(os.path.join(str(f[0]), "ir", ir_filename)))
                            error_cnt = error_cnt + 1
                    else:
                        logger.error("missing IR file: {}".format(os.path.join(str(f[0]), "ir", ir_filename)))
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
                            # os.stat() returns a stat_result, it is never == 0:
                            # the empty-file check never fired, use st_size
                            if os.stat(os.path.join(str(f[0]), "ir", ir_filename)).st_size == 0:
                                logger.error("empty IR file: {}".format(os.path.join(str(f[0]), "ir", ir_filename)))
                                error_cnt = error_cnt + 1
                        except:
                            logger.error("cannot stat IR file: {}".format(os.path.join(str(f[0]), "ir", ir_filename)))
                            error_cnt = error_cnt + 1
                    else:
                        logger.error("missing IR file: {}".format(os.path.join(str(f[0]), "ir", ir_filename)))
                        error_cnt = error_cnt + 1

            # if everything is there ... add folder to the compute list
            if error_cnt == 0:
                measure_folder_list.append(f[0])
                measure_audio_config_list.append(audio_config)
            else:
                # dropping the folder silently would produce a SOFA file with
                # fewer source positions than were actually measured, and still
                # exit clean. keep count and refuse to write below.
                logger.error("incomplete measure, folder skipped: {}".format(f[0]))
                measure_folder_skipped.append(f[0])

    #
    # create SOFA object and fetch impulses
    #
    if measure_folder_skipped:
        sys.exit(
            "\n[ERROR] {} incomplete measure folder(s), the SOFA file would be missing "
            "those source positions: {}".format(len(measure_folder_skipped), measure_folder_skipped)
        )

    if len(measure_folder_list) == 0:
        sys.exit("\n[ERROR] no complete measure folder found in: {}".format(yaml_params["measure_folder"]))

    measures_list = zip(measure_folder_list, measure_audio_config_list)
    if compute_sofa(audio_recording, measures_list, yaml_params):
        sys.exit("\n[ERROR] SOFA computation failed, no output file written.")
