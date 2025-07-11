#!/usr/bin/bash

args=("$@")

#wget -qO- --post-data ${args[0]} http://192.168.10.96/position/set

# this will convert angle in steps correclty now that the rotating-table
# uses the same auralysSpeaker firmware with stepper motor
../auralysSpeaker/cli/auralys_ctrl.py -rt ${args[0]}
