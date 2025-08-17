#!/usr/bin/env python3
"""Compute HRIR and save PYFAR/Wav format"""

from __future__ import division
import scipy.signal as sig

import os
import re
import sys
import glob
import yaml
import logging
import argparse

import matplotlib
import matplotlib.pyplot as plt
import matplotlib.mlab as mlab

import numpy as np
import pyfar as pf
import soundfile as sf
import scipy.signal as sig
from multiprocessing import Pool
from setproctitle import setproctitle

logger = logging.getLogger(__name__)

#
# DEFINES / CONSTANT / GLOBALS
#
_PLOT_SAVE_GRAPH = 0  # 0:skip, 1:save, 2:show, 3:show&save plot
_MIN_CPU_COUNT = 1  # we need at least one CPU for each compute process
_MIN_MEM_GB = 2.0  # min amount of memory for each compute process
_MAX_MEM_GB = 3.5  # max amount of memory for each compute process

# IR WINDOW FILTER, values in seconds
_IR_WINDOW_FADEIN_s = 0.002
_IR_WINDOW_FADEOUT_s = 0.002
_IR_WINDOW_LENGTH_s = 0.5

# IR_INFO for pyfar data storage
_IR_INFO_DELAY = 0
_IR_INFO_DELAY_SAMPLES = 1
_IR_INFO_dbFS_CALIB = 2
_IR_INFO_SAMPLERATE = 3

#
# fractional octave smoothing in pyfar is using many GB of RAM
# use with discretion when running only few threads in parallel.
_ENABLE_FRACTION_OCTAVE_SMOOTHING = False
_MAX_SMOOTHING_MEM_GB = 60


#
# receivers pair indication with ess_params naming for 3dti extraction
receivers_pairs = ["binaural", "array_six,front", "array_six,middle", "array_six,rear"]

_SOUND_SPEED = 343  # m/s


#
# TOOLS
#
def int_or_str(text):
    """Helper function for argument parsing."""
    try:
        return int(text)
    except ValueError:
        return text


#
# COMPUTE FUNCTIONS
#
def dbfft(x, fs, win=None, db_ref=None):
    N = len(x)  # Length of input sequence

    # compute window
    if win is None:
        win = np.ones(x.shape)

    # sanity check
    if len(x) != len(win):
        raise ValueError("Signal and window must be of the same length")

    # apply windowing
    x = x * win

    # Calculate real FFT and frequency vector
    sp = np.fft.rfft(x)
    freq = np.fft.rfftfreq(N, 1 / fs)  # np.arange((N / 2) + 1) / (float(N) / fs)

    # Scale the magnitude of FFT by window and factor of 2,
    # because we are using half of FFT spectrum.
    s_mag = np.abs(sp) * 2 / np.sum(win)

    s_phase = np.unwrap(np.angle(sp))
    # s_phase = np.angle(sp, deg=True)
    # s_phase[s_mag < 1] = 0

    # sp: convert to dBFS
    if db_ref is None:
        ref = s_mag.max()
    else:
        ref = db_ref

    s_dbfs = 20 * np.log10(s_mag / ref)

    return freq, s_dbfs, s_phase, ref


#
# compute reference stimulus signal (ESS)
#
def compute_ess(
    frequency_begin=20, frequency_end=20000, samplerate=96000, duration=15, amplitude=0.8, window=15, tail=False
):
    # exp sweep Parameters
    f1 = frequency_begin
    f2 = frequency_end
    fs = samplerate
    T = duration
    Tw = window

    if Tw > T:
        Tw = T

    # slew rate
    R = np.log(f2 / f1)

    t = np.arange(0, T, 1 / fs)
    data_full = amplitude * np.sin((2 * np.pi * f1 * T / R) * (np.exp(t * R / T) - 1))

    data = data_full

    if Tw != T:
        if tail:
            data = data_full[(T - Tw) * fs :]
        else:
            data = data_full[: Tw * fs]

    return data


#
# Impulse Response
#
def compute_hrir(folder=None):
    logger.info("compute_hrir: {}".format(folder))

    #
    # Load YAML config file
    #
    config = ""
    try:
        with open(os.path.join(str(folder), "config.yaml"), "r") as file:
            config = yaml.safe_load(file)
    except:
        logger.error("compute hrir: invalid config in folder {}".format(folder))
        return

    # supported syntax version
    ver_mjr = config["syntax"]["version"]["major"]
    ver_min = config["syntax"]["version"]["minor"]
    ver_rev = config["syntax"]["version"]["revision"]
    ver = ver_mjr + (ver_min / 10)
    if ver < 0.1:
        logger.error("compute_hrir: unsupported config syntax for {}".format(folder))
        return

    #
    # Read params from config
    #
    source_position = config["setup"]["sources"][0]["position"]["coord"]["value"]
    source_position_str = ",".join(str(x) for x in config["setup"]["sources"][0]["position_copy"]["coord"]["value"])

    setproctitle("hrir_" + "_".join(str(x) for x in config["setup"]["sources"][0]["position_copy"]["coord"]["value"]))

    audio_file = config["custom"]["audio_filename"]

    # Retrieve audio sweep parameters
    T = config["custom"]["stimulus"]["sweep"]["duration"]["value"]
    f1 = config["custom"]["stimulus"]["sweep"]["frequency"]["begin"]
    f2 = config["custom"]["stimulus"]["sweep"]["frequency"]["end"]
    padding_pre = config["custom"]["stimulus"]["sweep"]["padding"]["pre"]["value"]
    padding_post = config["custom"]["stimulus"]["sweep"]["padding"]["post"]["value"]
    tx_track_id = config["setup"]["sources"][0]["emitters"][0]["track_id"]
    rx_track_num = config["setup"]["listeners"][0]["receivers_count"]
    rx_track_id = config["setup"]["listeners"][0]["receivers"][0]["track_id"]

    # Select audio WAV file
    audio_format = config["custom"]["recording"]["format"]
    audio_subformat = config["custom"]["recording"]["subformat"]
    audio_file_ext = ""
    if "wav" == audio_format:
        audio_file_ext = "wav"
    else:
        logger.error(
            "compute hrir: source:{}, unsupported audio format for {} {}".format(
                source_position_str, folder, audio_format
            )
        )
        return

    logger.info("compute hrir: >>> source {}".format(source_position_str))

    # Load WAV file
    logger.info(
        "compute hrir: source "
        + source_position_str
        + ", audio file: "
        + str(folder)
        + "/"
        + audio_file
        + "."
        + audio_file_ext
    )

    data = ""
    data, samplerate = sf.read(str(folder) + "/" + audio_file + "." + audio_file_ext)
    fs = samplerate

    logger.info("compute hrir: source " + source_position_str + ", Duration: " + str(len(data) / fs) + "(s)")
    logger.info(
        "compute hrir: source "
        + source_position_str
        + ", Memory Buffer (24bit/s): "
        + str(T * 3 * fs / 1024)
        + "(Mbytes)"
    )

    samples = len(data)

    #
    # correlate and compute padding-pre sweep / recording latency
    #
    orig_sweep = compute_ess(
        frequency_begin=f1,
        frequency_end=f2,
        samplerate=samplerate,
        duration=T,
        amplitude=config["custom"]["stimulus"]["sweep"]["amplitude"]["value"],
        window=min(4, T),
        tail=False,
    )

    sweep_data_corr = sig.correlate(data[:, tx_track_id], orig_sweep)

    xsweep_head = np.argmax(abs(sweep_data_corr)) - int(len(orig_sweep))

    padding_pre_computed = xsweep_head

    if (xsweep_head) < (padding_pre * samplerate):
        logger.error(
            "compute hrir: source {}, invalid audio padding-pre: {:3.3f} (ms), expected {:3.3f} (ms)".format(
                source_position_str, (xsweep_head * 1000 / fs), (padding_pre * 1000)
            )
        )

    recording_latency_computed = np.argmax(abs(sweep_data_corr)) - int(len(orig_sweep) + padding_pre * samplerate)

    #
    # correlate and compute padding-post sweep
    #
    orig_sweep = compute_ess(
        frequency_begin=f1,
        frequency_end=f2,
        samplerate=samplerate,
        duration=T,
        amplitude=config["custom"]["stimulus"]["sweep"]["amplitude"]["value"],
        window=min(4, T),
        tail=True,
    )

    sweep_data_corr = sig.correlate(data[:, tx_track_id], orig_sweep)

    xsweep_tail = np.argmax(abs(sweep_data_corr))

    # sanity check: we need a valid duration
    if xsweep_tail <= xsweep_head:
        logger.error("compute hrir: source {}, audio sweep invalid head/tail position. skipping hrir computation.")
        return

    padding_post_computed = samples - xsweep_tail

    logger.info(
        "compute hrir: source {}, audio latency: {:3.3f} (ms) {} (samples)".format(
            source_position_str, recording_latency_computed * 1000 / fs, recording_latency_computed
        )
    )
    logger.info(
        "compute hrir: source {}, computed audio padding-pre: {:3.3f} (ms) {} (samples)".format(
            source_position_str, xsweep_head * 1000 / fs, xsweep_head
        )
    )
    logger.info(
        "compute hrir: source {}, computed audio padding-post: {:3.3f} (ms) {} (samples)".format(
            source_position_str, padding_post_computed * 1000 / fs, padding_post_computed
        )
    )

    logger.info(
        "compute hrir: source {}, computed sweep duration: {:3.3f} (ms) {} (samples)".format(
            source_position_str,
            (xsweep_tail - xsweep_head) * 1000 / fs,
            (xsweep_tail - xsweep_head),
        )
    )

    #
    # STIMULUS
    #

    # stimulus: this is the full signal
    xsweep_full = data[:, tx_track_id]

    # stimulus: remove loop-recording delay and paddings
    xsweep = data[xsweep_head:xsweep_tail, tx_track_id]

    # WORKAROUND :  LINUX ALSA AUDIO CARD, anti pop FADE-IN BIAS correction
    if 1:
        alsa_fade_in = np.linspace(0.8, 1, int(samplerate / 4))
        xsweep_full[xsweep_head : (xsweep_head + alsa_fade_in.size)] *= alsa_fade_in
        xsweep[0 : alsa_fade_in.size] *= alsa_fade_in

    # max/min
    # xsweep_max = np.max(np.abs(xsweep))
    # xsweep_min = np.min(xsweep)
    # if 1:
    #     plt.figure()
    #     plt.plot(xsweep_full)
    #     plt.show()
    #     plt.figure()
    #     plt.plot(xsweep)
    #     plt.show()

    # sweep duration from recorded signal
    T = (xsweep_tail - xsweep_head) / fs  # len(x) / fs

    #
    # Compute Inverse Sweep (for convolution computation) from the recorded stimulus
    #

    # compute timing range, sweep and total length
    t_sweep = np.arange(0, T * fs) / fs
    t = np.arange(0, len(xsweep)) / fs

    # compute inverse ESS slew-rate
    R = np.log(f2 / f1)

    # compute inverse mirror filter (equalized)
    k_sweep = np.exp(t_sweep * R / T)
    f = xsweep[::-1] / k_sweep

    # adding pre and post zero padding: note the signal is reversed as per A.Farina technique
    # so first we add padding-post, then padding-pre
    f = np.concatenate((np.zeros(padding_post_computed), f, np.zeros(padding_pre_computed)))

    # sanity check on filter length
    if len(f) != len(xsweep_full):
        logger.error(
            "compute hrir: source {}, ERROR: inverse sweep length is not the same as direct sweep lenth. id: {} track {}".format(
                source_position_str, str(rx_id), str(rx_track_id)
            ),
        )

    # pyfar: np.array to pyfar.signal class
    d_xsweep = pf.Signal(data=xsweep_full, sampling_rate=fs)
    i_xsweep = pf.Signal(data=f, sampling_rate=fs)

    # impulse response calibration for 0dB
    ir = d_xsweep * i_xsweep

    dbFS_calib = 2.38 * np.max(np.abs(ir.time))

    #
    # DEBUG ONLY: verify impulse response for ess sweep signal
    #             we want delay=0 and amplitude=0dbFS
    if 0:
        plt.figure()
        ax = pf.plot.time_freq(ir, dB_time=True, color=[0.6, 0.6, 0.6], label="ir raw", log_reference=1)
        pf.plot.time_freq(d_xsweep, dB_time=True, label="ess", log_reference=1)
        pf.plot.time_freq(i_xsweep, dB_time=True, label="inverse ess", log_reference=1)
        ax[0].set_xlim(0, 0.8)
        ax[0].set_ylim(-140, 0)
        ax[1].legend(loc="lower left")
        ax[0].set_title("Measured IR and TF, source: {}, CALIB=1".format(source_position_str))
        plt.show()

        plt.figure()
        ax = pf.plot.time_freq(ir, dB_time=True, color=[0.6, 0.6, 0.6], label="ir raw", log_reference=dbFS_calib)
        pf.plot.time_freq(d_xsweep, dB_time=True, label="ess", log_reference=dbFS_calib)
        pf.plot.time_freq(i_xsweep, dB_time=True, label="inverse ess", log_reference=dbFS_calib)
        ax[0].set_xlim(0, 0.8)
        ax[0].set_ylim(-140, 0)
        ax[1].legend(loc="lower left")
        ax[0].set_title("Measured IR and TF, source: {}, CALIB={}".format(source_position_str, str(dbFS_calib)))
        plt.show()

    #
    # loop over all the single-listener / multiple-receivers audio tracks
    #
    for rx_id in np.arange(rx_track_num):
        logger.info(
            "compute hrir: source {}, rx {}, STEP-00: analyze receiver id: {} track {}".format(
                source_position_str, str(rx_id), str(rx_id), str(rx_track_id)
            ),
        )

        # get the listener corrispondent audio track
        rx_track_id = config["setup"]["listeners"][0]["receivers"][rx_id]["track_id"]

        # this is the measured audio data in response to the ess stimulus
        x = data[:, rx_track_id]

        if _PLOT_SAVE_GRAPH:
            # separate plots in a subfolder
            plot_path = str(folder) + "/plots/"
            plot_path_pdf = str(folder) + "/plots/pdf/"
            plot_path_png = str(folder) + "/plots/png/"
            if not os.path.exists(plot_path):
                os.makedirs(plot_path)
            if not os.path.exists(plot_path_png):
                os.makedirs(plot_path_png)
            if not os.path.exists(plot_path_pdf):
                os.makedirs(plot_path_pdf)

            plt.rcParams["figure.figsize"] = [16, 9]
            plt.figure()
            plt.clf()
            plt.subplot(2, 1, 2)
            ax = plt.plot(x)
            plt.grid()
            plt.title("recorded_y(t), source {}".format(source_position_str))

            plt.subplot(2, 1, 1)
            ax = plt.plot(xsweep_full)
            plt.grid()
            plt.title("ess_sweep(t), source {}".format(source_position_str))

            # save / show plot
            if _PLOT_SAVE_GRAPH & 0x02:
                plt.show()
            if _PLOT_SAVE_GRAPH & 0x01:
                plot_filename = "{}_xy_rx_{}_trid_{}.pdf".format(audio_file, str(rx_id), str(rx_track_id))
                plt.savefig(plot_path_pdf + plot_filename, dpi=300)
                plot_filename = "{}_xy_rx_{}_trid_{}.png".format(audio_file, str(rx_id), str(rx_track_id))
                plt.savefig(plot_path_png + plot_filename, dpi=300)
            plt.close()

        #
        # compute IR (impulse response) with convolution in freq domain (fft)
        #
        logger.info(
            "compute hrir: source {}, rx {}, STEP-01: compute impulse response".format(source_position_str, str(rx_id))
        )
        #
        # IMPORTANT NOTE: the recording setup is equalized so that all the channels will have the same level recorded at
        #                 the same pressure level. See the section "calibration" of the config.yaml file for each
        #                 receiver and emitter. This is a critical step for a proper audio normalization

        # ToDo: equalize signal amplitude if the config file shows different calibration levels for emitters and receivers
        #       read calibration from config, convert dB to Linear, compute new amplitude

        # see config file for emitters and receivers at:
        #
        # calibration:
        #     whitenoise:
        #       spl_1m_dbA_slow: 60
        #       wav_peak_level: 0.8
        #     sine-1khz:
        #       spl_1m_dbA_slow: 60
        #       wav_peak_level: 0.8

        # pyfar: np.array to pyfar.signal class
        x_rec = pf.Signal(data=x, sampling_rate=fs)

        logger.info(
            "compute hrir: source {}, rx {}, STEP-02a: compute IR signal (pyfar)".format(
                source_position_str, str(rx_id)
            )
        )

        #
        # IR by convolution (FFT multiply)
        ir = x_rec * i_xsweep

        # 0dbFS calibration: retrieve 0 dBFS level from reference sweep amplitude
        ir = pf.multiply((ir, 1 / dbFS_calib), domain="time")

        # compute IR delay

        # using pyfar is actually slower...
        # ir_delay= pf.dsp.find_impulse_response_delay(ir)

        # so going with max correlation in time,
        # since we know the distance we keep a "SAFETY SEARCH WINDOW" in case
        # we have a non ideal recording environment: the first DIRECT reflection
        # is travelling at the sound speed, we keep twice the distance

        distance_sound_delay = 2 * (source_position[2] / _SOUND_SPEED)

        # ir_delay_samples = np.argmax( np.abs( ir.time ) )
        ir_delay_samples = np.argmax(np.abs(ir.time[:, : int(distance_sound_delay * fs)]))

        # ir_delay = np.argmax(np.abs(ir.time)) / fs
        ir_delay = ir_delay_samples / fs

        logger.info(
            "compute hrir: source {}, rx {}, STEP-02b: IR delay={} [ms]".format(
                source_position_str, str(rx_id), (ir_delay * 1000)
            )
        )

        # normalize in comparison to the recorded signal amplitude
        logger.info(
            "compute hrir: source {}, rx {}, STEP-03: normalize IR signal to {}".format(
                source_position_str, str(rx_id), dbFS_calib
            )
        )

        # ToDo: still need the amplited eq above, so copy as-is
        ir_norm = ir

        if _PLOT_SAVE_GRAPH:
            if _ENABLE_FRACTION_OCTAVE_SMOOTHING:
                # impulse response, smoothed 1/6 octave band

                # NOTE: since "smooth_fractiona_octave" is allocating 6G of ram we use it ONLY for plots
                #       enabling this will decrease the number of parallel computations based on the number of cores and
                #       available memory of the system
                # see: https://pyfar.readthedocs.io/en/stable/modules/pyfar.dsp.html#pyfar.dsp.smooth_fractional_octave
                logger.info(
                    "compute hrir: source {}, rx {}, STEP-04: post-process IR signal, smooth 1/6th octave".format(
                        source_position_str, str(rx_id)
                    )
                )
                ir_norm_smooth, _ = pf.dsp.smooth_fractional_octave(
                    ir_norm, num_fractions=6, mode="magnitude_zerophase"
                )

        #
        # compute cropped IR (window)
        #
        logger.info(
            "compute hrir: source {}, rx {}, STEP-05: post-process IR signal, high-pass & window".format(
                source_position_str, str(rx_id)
            )
        )

        # apply high-pass (8th order) at 20Hz to reject out of band noise
        ir_norm_hipass = pf.dsp.filter.butterworth(ir_norm, 8, f1, "highpass")

        # apply window to reduce impulse response length
        dyn_fade_s = (int((1000 * source_position[2] / _SOUND_SPEED) / 2) + 1) / 1000

        # ir_norm_hipass_window = pf.dsp.time_window(
        #     ir_norm_hipass,
        #     [0, _IR_WINDOW_FADEIN_s, _IR_WINDOW_LENGTH_s, (_IR_WINDOW_LENGTH_s + _IR_WINDOW_FADEOUT_s)],
        #     unit="s",
        #     crop="window",
        # )

        ir_norm_hipass_window = pf.dsp.time_window(
            ir_norm_hipass,
            [0, dyn_fade_s, _IR_WINDOW_LENGTH_s, (_IR_WINDOW_LENGTH_s + 2 * dyn_fade_s)],
            unit="s",
            crop="window",
        )

        # apply smoothing for 1/6 octave band
        ir_norm_hipass_window_smooth, _ = pf.dsp.smooth_fractional_octave(
            ir_norm_hipass_window, num_fractions=6, mode="magnitude_zerophase"
        )

        if _PLOT_SAVE_GRAPH:
            # separate plots in a subfolder
            plot_path = str(folder) + "/plots/"
            plot_path_pdf = str(folder) + "/plots/pdf/"
            plot_path_png = str(folder) + "/plots/png/"
            if not os.path.exists(plot_path):
                os.makedirs(plot_path)
            if not os.path.exists(plot_path_png):
                os.makedirs(plot_path_png)
            if not os.path.exists(plot_path_pdf):
                os.makedirs(plot_path_pdf)

            # NOTE: since IR has been calibrated to 0dB from the d_xsweep and i_xsweep, all the plots
            #       can be done using log_reference=1 for 0dB level.

            if 1:
                plt.rcParams["figure.figsize"] = [16, 9]
                plt.figure()
                ax = pf.plot.time_freq(ir, dB_time=True, color=[0.6, 0.6, 0.6], label="raw", log_reference=1)
                pf.plot.time_freq(ir_norm_hipass_window, dB_time=True, label="post-processed", log_reference=1)
                ax[0].set_xlim(0, 0.8)
                ax[0].set_ylim(-140, 0)
                ax[1].legend(loc="lower left")
                ax[0].set_title(
                    "Measured IR and TF, source: {}, listener_rx: {}, track_id: {}".format(
                        source_position_str, str(rx_id), str(rx_track_id)
                    )
                )
                # save / show plot
                if _PLOT_SAVE_GRAPH & 0x02:
                    plt.show()
                if _PLOT_SAVE_GRAPH & 0x01:
                    plot_filename = "{}_ir_tf_rx_{}_trid_{}.pdf".format(audio_file, str(rx_id), str(rx_track_id))
                    plt.savefig(plot_path_pdf + plot_filename, dpi=300)
                    plot_filename = "{}_ir_tf_rx_{}_trid_{}.png".format(audio_file, str(rx_id), str(rx_track_id))
                    plt.savefig(plot_path_png + plot_filename, dpi=300)
                # cleanup
                plt.close()

            if 1:
                plt.rcParams["figure.figsize"] = [16, 9]
                plt.figure()
                ax = pf.plot.freq(ir, dB=True, label="Original HRTF", color="grey", log_reference=1)
                if _ENABLE_FRACTION_OCTAVE_SMOOTHING:
                    pf.plot.freq(
                        ir_norm_smooth,
                        dB=True,
                        label="Original (1/6th octave) HRTF",
                        color="blue",
                        log_reference=1,
                    )
                pf.plot.freq(
                    ir_norm_hipass_window_smooth,
                    dB=True,
                    label="Filtered HRTF (hipass, crop, smooth)",
                    color="red",
                    log_reference=1,
                )
                ax.set_title(
                    "Measured TF, source: {}, listener_rx: {}, track_id: {}".format(
                        source_position_str, str(rx_id), str(rx_track_id)
                    )
                )
                ax.legend()
                # save / show plot
                if _PLOT_SAVE_GRAPH & 0x02:
                    plt.show()
                if _PLOT_SAVE_GRAPH & 0x01:
                    plot_filename = "{}_tfs_rx_{}_trid_{}.pdf".format(audio_file, str(rx_id), str(rx_track_id))
                    plt.savefig(plot_path_pdf + plot_filename, dpi=300)
                    plot_filename = "{}_tfs_rx_{}_trid_{}.png".format(audio_file, str(rx_id), str(rx_track_id))
                    plt.savefig(plot_path_png + plot_filename, dpi=300)
                # cleanup
                plt.close()

        # For the purpose of reproducibility save intermediate results in a compressed file format.
        # pyfar uses its own far format, which saves data in zip format.
        if 1:
            logger.info(
                "compute hrir: source {}, rx {}, STEP-06: save results for receiver: {}".format(
                    source_position_str, str(rx_id), rx_id
                )
            )

            # separate plots in a subfolder
            ir_path = str(folder) + "/ir/"
            if not os.path.exists(ir_path):
                os.makedirs(ir_path)

            ir_filename = "{}_IR_rx_{}_trid_{}.far".format(audio_file, str(rx_id), str(rx_track_id))

            ir_info = np.array([ir_delay, ir_delay_samples, dbFS_calib, samplerate])

            pf.io.write(
                ir_path + ir_filename,
                compressed=True,
                ir=ir,
                ir_norm_hipass_window=ir_norm_hipass_window,
                ir_info=ir_info,
            )

            logger.info(
                "compute hrir: source {}, rx {}, STEP-07: save IR in wav format for receiver: {}".format(
                    source_position_str, str(rx_id), rx_id
                )
            )

            #
            # For the final result, saving also in .WAV
            #

            # NOTE: audio wav files have max amplitude of -1/+1, which is 0dbFS,
            #       do we need to adjust for real/measured 0dbFS ?
            ir_filename = "{}_IR_rx_{}_trid_{}.wav".format(audio_file, str(rx_id), str(rx_track_id))
            pf.io.write_audio(ir, ir_path + ir_filename, "DOUBLE")

            ir_filename = "{}_IR-filtered_rx_{}_trid_{}.wav".format(audio_file, str(rx_id), str(rx_track_id))
            pf.io.write_audio(ir_norm_hipass_window, ir_path + ir_filename, "DOUBLE")

            # for easier documentation write result also in yaml file
            ir_results = {
                "syntax": {"name": "ir_results", "version": {"major": 0, "minor": 1, "revision": 0}},
                "ir_delay": str(ir_delay),
                "ir_delay_samples": str(ir_delay_samples),
                "dbFS_calib": str(dbFS_calib),
                "ir_samples": str(ir.n_samples),
                "ir_norm_hipass_window_samples": str(ir_norm_hipass_window.n_samples),
                "samplerate": str(samplerate),
            }
            yaml_filename = "{}_IR_rx_{}_trid_{}.yaml".format(audio_file, str(rx_id), str(rx_track_id))
            try:
                with open(ir_path + yaml_filename, "w") as outfile:
                    yaml.dump(ir_results, outfile, default_flow_style=False)
            except:
                logger.error(
                    "compute hrir: source {}, rx {}, ERROR saving YAML results for receiver: {}".format(
                        source_position_str, str(rx_id), rx_id
                    )
                )

            #
            # DEBUG: convolve to check result from the same input signal
            #
            if 0:
                test_output = d_xsweep * pf.dsp.pad_zeros(
                    ir_norm_hipass_window, (d_xsweep.n_samples - ir_norm_hipass_window.n_samples)
                )
                plt.figure()
                # pf.plot.time_freq(test_output, label="check result", color="red", log_reference=dbFS_calib)
                pf.plot.time(test_output, label="ess*ir", color="red")
                pf.plot.time(x_rec, label="reference", color="blue")
                plt.show()

    logger.info("compute hrir: <<< source: " + source_position_str + " done.")


#
###############################################################################
# MAIN
###############################################################################
#
if __name__ == "__main__":
    setproctitle("compute_hrir_main")

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
            help="folder with audio sweep measure results (default: %(default)s)",
        )
        parser.add_argument(
            "-c",
            "--cpu_process",
            default=6,
            type=int,
            help="maximum number of CPU process to use (default: %(default)s)",
        )
        parser.add_argument(
            "-g",
            "--graphs",
            type=str,
            default="skip",
            help="skip, save, show, show_and_save (default: %(default)s)",
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

    measure_folder_list = []

    #
    # walk the given folder and search for proper results
    #
    if not (os.path.isdir(yaml_params["measure_folder"])):
        sys.exit("\n[ERROR] cannot open folder: {}".format(yaml_params["measure_folder"]))

    for f in os.walk(yaml_params["measure_folder"]):
        if os.path.exists(os.path.join(str(f[0]), "config.yaml")):
            audio_config = ""
            try:
                with open(os.path.join(str(f[0]), "config.yaml"), "r") as file:
                    audio_config = yaml.safe_load(file)
            except:
                sys.exit("\n[ERROR] cannot open/parse yaml config file: {}".format(kwargs["ess_yaml_config"]))

            # add folder to the list of measures only if a valid config is found
            try:
                if audio_config["syntax"]["name"] == "audio_measure":
                    measure_folder_list.append(f[0])
            except:
                pass

    #
    # compute process pool size based on CPU/MEM requirements
    #
    mem_bytes = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")  # e.g. 4015976448
    mem_gib = mem_bytes / (1024.0**3)  # e.g. 3.74
    cpu_count = min([(os.cpu_count() - 2), yaml_params["cpu_process"]])
    cpu_count = max([_MIN_CPU_COUNT, cpu_count])

    if _PLOT_SAVE_GRAPH == 0:
        max_pool_size = min(cpu_count, int(mem_gib / _MIN_MEM_GB))
    else:
        max_pool_size = min(cpu_count, int(mem_gib / _MAX_MEM_GB))
        if _MAX_SMOOTHING_MEM_GB:
            max_pool_size = min(cpu_count, int(mem_gib / _MAX_SMOOTHING_MEM_GB))

    #
    # compute HRIR for each measure folder
    #
    logger.info("Pool size: {}".format(max_pool_size))
    cpu_pool = Pool(max_pool_size)

    if len(measure_folder_list) > 0:
        # debug: single manual run
        # compute_hrir(measure_folder_list[0])

        # with cpu_pool as w:
        #     # w.map(partial(compute_hrir, config=None), measure_folder_list)
        #     w.map_async(compute_hrir, measure_folder_list, callback=progress)
        result = cpu_pool.map(compute_hrir, measure_folder_list)

    cpu_pool.close()
    cpu_pool.join()
