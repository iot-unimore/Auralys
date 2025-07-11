#!/usr/bin/bash

SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"

args=("$@")

# this will convert angle in steps correclty now that the rotating-table
# uses the same auralysSpeaker firmware with stepper motor
#$SCRIPT_DIR/../auralysSpeaker/cli/auralys_ctrl.py -rt ${args[0]}

# this is temporary until we fully switch to auralysSpeaker commands
angle=$(echo "(${args[0]} * (2454840/360))"  | tr -d '\r' | bc -l)
mks_steps=$( echo "${angle}" | awk '{print int($1+0.5)}' )


wget -qO- --post-data ${mks_steps} http://192.168.10.96/position/set
