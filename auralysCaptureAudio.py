#!/usr/bin/env python3
"""Auralys Speaker 3D positionig and mapping audio recording"""

import argparse
import logging
import sys
import asyncio
import yaml
import time
import subprocess
import multiprocess
import os

logger = logging.getLogger(__name__)



#
# DEFINES / CONSTANT / GLOBALS
#
_ROOT_DIR = os.path.abspath(os.path.dirname(__file__))
_CMD_DIR = os.path.join(_ROOT_DIR, "./hrtf")
_AURALIS_DIR = os.path.join(_ROOT_DIR,"./auralysSpeaker")
_HRTF_DIR = os.path.join(_ROOT_DIR,"./hrtf")
_AUDIO_DIR = os.path.join(_ROOT_DIR,"./audio")

_AZIMUT_BEGIN = 360
_AZIMUT_END = 1
_AZIMUT_STEP = -10

_AUDIO_MAP_CFG_NAME="audio_map_params"
_AUDIO_CFG_NAME="audio_params"

# Use alternating pattern for AZIMUTH position
_USE_ALTERNATE_AZIMUTH = True

# AUDIO CARD USB IDs
_AUDIO_RECORDING_DEVICE_ID = "Fireface UFX (23703154)"
_AUDIO_PLAYBACK_DEVICE_ID = "Scarlett 2i2 USB"

#
# EXECUTABLES / EXTERNAL CMDs
#
_FFMPEG_EXE = "/usr/bin/ffmpeg"
_FFPROBE_EXE = "/usr/bin/ffprobe"
_APLAY_EXE = "/usr/bin/aplay"


# Define a Speaker 3D Position Table with 3 columns [azimuth, X, Z] (Y=0) and 10 rows (i.e. 10 positions)
auralysPositions = [
    # [75,  259, 2616],
    # [60,  500, 2516],
    [45, 707, 2490],
    [30, 866, 2200],
    [15, 910, 2000],
    [0, 1000, 1650],
    [-15, 960, 1391],
    [-30, 870, 1100],
    [-45, 800, 900],
    # [-60, 500,  784],
    # [-75, 259,  684]
]

_VERSE_PATH="./"

verseVoicesPlayList =[
    ["unimore","000007_voice"],
    ["unimore","000005_voice"],
    ["unimore","000004_voice"],
]


########################################################################################################################
#  DO NOT MODIFY CODE BELOW THIS LINE
########################################################################################################################


#
# TOOLS
#
def find_audio_card():
    audio_recording_hw_idx = 0
    audio_playback_hw_idx = 0

    # search for RECORDING card
    try:
        rv = subprocess.check_output([_APLAY_EXE+' -l | grep "'+_AUDIO_RECORDING_DEVICE_ID+'"'], shell=True)
        if "card" in rv.decode():
            audio_recording_hw_idx = (rv.decode().split(":"))[0]
            audio_recording_hw_idx = (audio_recording_hw_idx.split(" "))[1]
            # print(audio_recording_hw_idx)
        else:
            print(f"ERROR: cannot find recording audio card {_AUDIO_RECORDING_DEVICE_ID}, exit.")
            exit(0)
    except:
        print(f"ERROR: cannot find recording audio card {_AUDIO_RECORDING_DEVICE_ID}, exit.")
        exit(1)

    # search for PLAYBACK card
    try:
        rv = subprocess.check_output([_APLAY_EXE+' -l | grep "'+_AUDIO_PLAYBACK_DEVICE_ID+'"'], shell=True)
        if "card" in rv.decode():
            audio_playback_hw_idx = (rv.decode().split(":"))[0]
            audio_playback_hw_idx = (audio_playback_hw_idx.split(" "))[1]
            print(audio_playback_hw_idx)
        else:
            print(f"ERROR: cannot find recording audio card {_AUDIO_PLAYBACK_DEVICE_ID}, exit.")
            exit(0)
    except:
        print(f"ERROR: cannot find recording audio card {_AUDIO_PLAYBACK_DEVICE_ID}, exit.")
        exit(0)

    return [audio_recording_hw_idx, audio_playback_hw_idx]


def update_audio_map_params(
    input_file_path, output_file_path, elevation_begin, elevation_end, hw_recoding_idx, hw_playback_idx
):
    """
    Reads a YAML file, updates 'elevation_begin' and 'elevation_end' fields,
    and writes the modified content to a new file.

    Parameters:
        input_file_path (str): Path to the input YAML file.
        output_file_path (str): Path to save the modified YAML file.
        elevation_begin (float or int): New value for 'elevation_begin'.
        elevation_end (float or int): New value for 'elevation_end'.
    """
    # Read the YAML file
    with open(input_file_path, "r") as file:
        data = yaml.safe_load(file)

    # Update the fields
    data["elevation_begin"] = int(elevation_begin)
    data["elevation_end"] = int(elevation_end)

    data["input_device"] = "hw:" + hw_recoding_idx + ",0"
    data["output_device"] = "hw:" + hw_playback_idx + ",0"

    # voices to play
    data["verseVoicesPlayList"] = verseVoicesPlayList

    # Write the modified YAML to the output file
    with open(output_file_path, "w") as file:
        yaml.safe_dump(data, file, default_flow_style=False)


#
# MAIN
#

if __name__ == "__main__":
    hw_rec_idx = 0
    hw_play_idx = 0

    #
    # check for usb card idx
    #
    [hw_rec_idx, hw_play_idx] = find_audio_card()

    #
    # sanity checks on azimut begin/end
    #
    if _AZIMUT_STEP == 0:
        print("invalid azimut step, exiting")
        exit(1)
    elif _AZIMUT_STEP > 0:
        if _AZIMUT_BEGIN > _AZIMUT_END:
            print("invalid azimut begin/end and step combination, exiting")
            exit(1)
    elif _AZIMUT_STEP < 0:
        if _AZIMUT_BEGIN < _AZIMUT_END:
            print("invalid azimut begin/end and step combination, exiting")
            exit(1)

    #
    # ESS mapping
    #
    idx = 0
    for row in auralysPositions:
        print("==============================================================")
        position = str(row[1]) + ",0," + str(row[2])
        print("AURALYS SPEAKER ELEV: " + str(row[0]) + "(deg), CARTESIAN XYZ POS: " + position + "mm")
        print("==============================================================")

        # move speaker in position
#        rv = subprocess.run([_AURALIS_DIR+"/auralysSpeaker/cli/auralys_ctrl.py","-c","set","position","-p",str(position),"-rs",str(-1 * int(row[0])),"-t","ac","-v",],stdout=subprocess.PIPE).stdout.decode("utf-8")

        # wait for stabilization of the speaker
        time.sleep(3)

        # compute real azimut begin/end values
        azimuth_begin = _AZIMUT_BEGIN
        azimuth_end = _AZIMUT_END
        if _USE_ALTERNATE_AZIMUTH == True:
            if (idx % 2) == 0:
                azimuth_begin = int(_AZIMUT_BEGIN + (_AZIMUT_STEP / 2))
                azimuth_end = int(_AZIMUT_END + (_AZIMUT_STEP / 2))

        # for next iteration
        idx += 1

        # clipping
        azimuth_begin = min(360, max(azimuth_begin, 0))
        azimuth_end = min(360, max(azimuth_end, 0))

        #
        # update params for new elevation
        #
        update_audio_map_params(
            _AUDIO_DIR+"/"+_AUDIO_MAP_CFG_NAME+".yaml", "/tmp/"+_AUDIO_MAP_CFG_NAME+".yaml", str(row[0]), str(row[0]), hw_rec_idx, hw_play_idx
        )

        #
        # record audio voices
        #

        # step 10 deg, SWEEP
        # rv = subprocess.run(["./hrtf/record_ess_map.py","-v","-yp","/tmp/ess_map_params.yaml","-yc" ,"./hrtf/ess_params.yaml","-ab","360","-ae","5","-as","-10","-m","/media/gfilippi/audiodata/wilsonClean_20250809-001","-n","wilsonClean"], stdout=subprocess.PIPE).stdout.decode("utf-8")

        rv = subprocess.run(
            [
                _AUDIO_DIR+"/record_audio_map.py",
                "-v",
                "-yp",
                "/tmp/"+_AUDIO_MAP_CFG_NAME+".yaml",
                "-yc",
                _AUDIO_DIR+"/"+_AUDIO_CFG_NAME+".yaml",
                "-ab",
                str(azimuth_begin),
                "-ae",
                str(azimuth_end),
                "-as",
                str(_AZIMUT_STEP),
                "-m",
                "/media/gfilippi/audiodata/wilsonAudio_20250809-001",
                "-n",
                "wilsonAudio",
                "-t",
            ],
            stdout=subprocess.PIPE,
        ).stdout.decode("utf-8")

    time.sleep(3)

    # back to zero position: speaker & table
#    rv = subprocess.run([_AURALIS_DIR+"/cli/auralys_ctrl.py", "-c", "cmd", "gozero", "-rs", "0", "-rt", "0", "-v"],stdout=subprocess.PIPE).stdout.decode("utf-8")
