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
    [30,  953, 2300],
    [15,  1063,2035],
    [0,   1100,1750],
    [-15, 1063,1465],
    [-30, 953, 1200],
    [-45, 778,  972],
    # [-60, 550,  797],
    # [-75, 285,  687]
]


#
# MAIN
#

if __name__ == "__main__":

    for row in auralysPositions:

        position=str(row[1])+",0,"+str(row[2])
        print(position)

        # move speaker in position
        rv = subprocess.run(["./auralysSpeaker/cli/auralys_ctrl.py","-c","set", "position", "-p", str(position), "-r", str(-1*int(row[0])), "-t", "ac", "-v", ], stdout=subprocess.PIPE).stdout.decode("utf-8")

        # wait for stabilization of the speaker
        time.sleep(3)
        
        # record ess map
        # rv = subprocess.run(["./hrtf/record_ess_map.py","-v","-yp","./hrtf/ess_map_params.yaml","-yc" ,"./hrtf/ess_params.yaml","-ab","360","-ae","1","-as","-90","-m","./hrtf/measures/test","-n","test","-t"], stdout=subprocess.PIPE).stdout.decode("utf-8")

        rv = subprocess.run(["./hrtf/record_ess_map.py","-v","-yp","./hrtf/ess_map_params.yaml","-yc" ,"./hrtf/ess_params.yaml","-ab","360","-ae","190","-as","-45","-m","./hrtf/measures/test","-n","test","-t"], stdout=subprocess.PIPE).stdout.decode("utf-8")
        
        print("--")
        

    time.sleep(3)

    # back to zero position: speaker

    rv = subprocess.run(["./auralysSpeaker/cli/auralys_ctrl.py","-c","cmd", "gozero", "-r", "0", "-t", "ac", "-v", ], stdout=subprocess.PIPE).stdout.decode("utf-8")

    # back to zero position: rotating table

    rv = subprocess.run(["./hrtf/cmd_set_position.sh","0"], stdout=subprocess.PIPE).stdout.decode("utf-8")
