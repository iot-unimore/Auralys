#!/usr/bin/bash

args=("$@")

output=$(wget -qO- http://192.168.10.96/position/get)

mks_steps=$(echo "$output" | grep '"encoder"' | awk -F': ' '{print $2}' | tr -d ',')

# this is temporary until we fully switch to auralysSpeaker commands
angle=$(echo "($mks_steps * (360.0/2454840))"  | tr -d '\r' | bc -l)

angle_int=$(echo "$angle" | awk '{print int($1+0.5)}')

output_yaml=$(echo "$output" | sed -E "s/\"encoder\"[[:space:]]*:[[:space:]]*[0-9]+/\"position\": $angle_int/")

echo "$output_yaml"
