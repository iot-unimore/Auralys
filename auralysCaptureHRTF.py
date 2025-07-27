#!/usr/bin/env python3
"""Auralys Speaker 3D position control"""

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

# Define a table with 3 columns and 10 rows
auralysPositions = [
    # [75,  259, 2616],
    # [60,  500, 2516],
    [45,  707,  2490],
    [30,  866,  2200],
    [15,  910,  2000],
    [0,   1000, 1650],
    [-15, 960,  1391],
    [-30, 870,  1100],
    [-45, 800,   900],
    # [-60, 500,  784],
    # [-75, 259,  684]
]


#
# TOOLS
#

def find_audio_card():
    audio_recording_hw_idx = 0
    audio_playback_hw_idx = 0

    # search for RECORDING card
    rv = subprocess.check_output(["aplay -l | grep \"Fireface UFX (23703154)\""], shell=True)
    if "card" in rv.decode():
        audio_recording_hw_idx = (rv.decode().split(":"))[0]
        audio_recording_hw_idx = (audio_recording_hw_idx.split(" "))[1]
        print(audio_recording_hw_idx)
    else:
        print("ERROR: cannot find recording audio card Fireface UFX (23703154), exit.")
        exit(0)

    # search for PLAYBACK card
    rv = subprocess.check_output(["aplay -l | grep \"Scarlett 2i2 USB\""], shell=True)
    if "card" in rv.decode():
        audio_playback_hw_idx = (rv.decode().split(":"))[0]
        audio_playback_hw_idx = (audio_playback_hw_idx.split(" "))[1]
        print(audio_playback_hw_idx)
    else:
        print("ERROR: cannot find recording audio card Scarlett 2i2 USB, exit.")
        exit(0)

    return [audio_recording_hw_idx, audio_playback_hw_idx]



def update_ess_map_params(input_file_path, output_file_path, elevation_begin, elevation_end, hw_recoding_idx, hw_playback_idx):
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
    with open(input_file_path, 'r') as file:
        data = yaml.safe_load(file)

    # Update the fields
    data['elevation_begin'] = int(elevation_begin)
    data['elevation_end'] = int(elevation_end)

    data['input_device'] = "hw:"+hw_recoding_idx+",0"
    data['output_device'] = "hw:"+hw_playback_idx+",0"

    # Write the modified YAML to the output file
    with open(output_file_path, 'w') as file:
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
    # ESS mapping
    #
    for row in auralysPositions:

        print("==============================================================")
        position=str(row[1])+",0,"+str(row[2])
        print("AURALYS SPEAKER ELEV: "+str(row[0])+"(deg), CARTESIAN XYZ POS: "+position+"mm")
        print("==============================================================")

        # move speaker in position
        rv = subprocess.run(["./auralysSpeaker/cli/auralys_ctrl.py","-c","set", "position", "-p", str(position), "-rs", str(-1*int(row[0])), "-t", "ac", "-v" ], stdout=subprocess.PIPE).stdout.decode("utf-8")

        # wait for stabilization of the speaker
        time.sleep(3)


        #
        # update params for new elevation
        #
        update_ess_map_params("./hrtf/ess_map_params.yaml", "/tmp/ess_map_params.yaml", str(row[0]), str(row[0]), hw_rec_idx, hw_play_idx)

        #
        # record ess map
        #

        # step 45 deg, DRY-RUN
        # rv = subprocess.run(["./hrtf/record_ess_map.py","-v","-yp","/tmp/ess_map_params.yaml","-yc" ,"./hrtf/ess_params.yaml","-ab","360","-ae","1","-as","-45","-m","./hrtf/measupres/test","-n","test","-t"], stdout=subprocess.PIPE).stdout.decode("utf-8")

        # step 90 deg, DRY-RUN
        #rv = subprocess.run(["./hrtf/record_ess_map.py","-v","-yp","/tmp/ess_map_params.yaml","-yc" ,"./hrtf/ess_params.yaml","-ab","360","-ae","5","-as","-180","-m","./hrtf/measures/test","-n","test","-t"], stdout=subprocess.PIPE).stdout.decode("utf-8")

        # step 120 deg, SWEEP
        #rv = subprocess.run(["./hrtf/record_ess_map.py","-v","-yp","/tmp/ess_map_params.yaml","-yc" ,"./hrtf/ess_params.yaml","-ab","360","-ae","5","-as","-120","-m","./hrtf/measures/test","-n","test"], stdout=subprocess.PIPE).stdout.decode("utf-8")


        # step 10 deg, SWEEP
        rv = subprocess.run(["./hrtf/record_ess_map.py","-v","-yp","/tmp/ess_map_params.yaml","-yc" ,"./hrtf/ess_params.yaml","-ab","360","-ae","5","-as","-10","-m","/media/gfilippi/audiodata/wilsonClean_20250725-001","-n","wilsonClean"], stdout=subprocess.PIPE).stdout.decode("utf-8")

    time.sleep(3)

    # back to zero position: speaker & table
    rv = subprocess.run(["./auralysSpeaker/cli/auralys_ctrl.py","-c","cmd", "gozero", "-rs", "0", "-rt", "0", "-v" ], stdout=subprocess.PIPE).stdout.decode("utf-8")
