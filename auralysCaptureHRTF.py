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
    # [75,  285, 2813],
    # [60,  550, 2703],
    # [45,  778, 2528],
#    [30,  953, 2300],
    [15,  1063,2035],
    [0,   1100,1750],
    [-15, 1063,1465],
#    [-30, 953, 1200],
#    [-45, 778,  972],
    # [-60, 550,  797],
    # [-75, 285,  687]
]

#
# TOOLS
#
def update_ess_map_params(input_file_path, output_file_path, elevation_begin, elevation_end):
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

    # Write the modified YAML to the output file
    with open(output_file_path, 'w') as file:
        yaml.safe_dump(data, file, default_flow_style=False)

#
# MAIN
#

if __name__ == "__main__":

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
        update_ess_map_params("./hrtf/ess_map_params.yaml", "/tmp/ess_map_params.yaml", str(row[0]), str(row[0]))

        #
        # record ess map
        #

        # step 45 deg, DRY-RUN
        # rv = subprocess.run(["./hrtf/record_ess_map.py","-v","-yp","/tmp/ess_map_params.yaml","-yc" ,"./hrtf/ess_params.yaml","-ab","360","-ae","1","-as","-45","-m","./hrtf/measures/test","-n","test","-t"], stdout=subprocess.PIPE).stdout.decode("utf-8")

        # step 90 deg, DRY-RUN
        rv = subprocess.run(["./hrtf/record_ess_map.py","-v","-yp","/tmp/ess_map_params.yaml","-yc" ,"./hrtf/ess_params.yaml","-ab","360","-ae","5","-as","-90","-m","./hrtf/measures/test","-n","test","-t"], stdout=subprocess.PIPE).stdout.decode("utf-8")
        
        # step 120 deg, SWEEP
        #rv = subprocess.run(["./hrtf/record_ess_map.py","-v","-yp","/tmp/ess_map_params.yaml","-yc" ,"./hrtf/ess_params.yaml","-ab","360","-ae","5","-as","-120","-m","./hrtf/measures/test","-n","test"], stdout=subprocess.PIPE).stdout.decode("utf-8")
        
    time.sleep(3)

    # back to zero position: speaker & table
    rv = subprocess.run(["./auralysSpeaker/cli/auralys_ctrl.py","-c","cmd", "gozero", "-rs", "0", "-rt", "0", "-v" ], stdout=subprocess.PIPE).stdout.decode("utf-8")
