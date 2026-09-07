#!/usr/bin/bash

if [ $# -eq 0 ]
  then
    echo "No arguments supplied, needs Auralys measurement folder path"
    exit
fi

if [ $# -eq 2 ]
 then
   ./compute_hrir.py -v -c 44 -d 0.0009 -mf $1 --log $2
 else
   ./compute_hrir.py -v -c 44 -d 0.0009 -mf $1
fi

# fix array positioning from measures before computing SOFA FILES
#./tools/compute_array_positioning.py -i $1 -l binaural array_six -q
./tools/compute_array_positioning.py -i $1 -l binaural array_six -q --fix

#./compute_sofa.py -v -c 88 -mf $1
./compute_3dti_sofa.py -v -c 88 -mf $1 -irw 0.300 -x ambisonic -z -s binaural
./compute_3dti_sofa.py -v -c 88 -mf $1 -irw 0.300 -x ambisonic -z -s array_six,front
./compute_3dti_sofa.py -v -c 88 -mf $1 -irw 0.300 -x ambisonic -z -s array_six,middle
./compute_3dti_sofa.py -v -c 88 -mf $1 -irw 0.300 -x ambisonic -z -s array_six,rear
