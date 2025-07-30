#!/usr/bin/bash

if [ $# -eq 0 ]
  then
    echo "No arguments supplied, needs Auralys measurement folder path"
    exit
fi

if [ $# -eq 2 ]
 then
   ./compute_hrir.py -v -c 44 -mf $1 --log $2
 else
   ./compute_hrir.py -v -c 44 -mf $1
fi

./compute_sofa.py -v -c 88 -mf $1
./compute_3dti_sofa.py -v -c 88 -mf $1 -irw 0.02 -z -s binaural
./compute_3dti_sofa.py -v -c 88 -mf $1 -irw 0.02 -z -s array_six,front
./compute_3dti_sofa.py -v -c 88 -mf $1 -irw 0.02 -z -s array_six,middle
./compute_3dti_sofa.py -v -c 88 -mf $1 -irw 0.02 -z -s array_six,rear
