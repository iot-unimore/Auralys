#!/usr/bin/env python3
"""mux a multi-track wav file into the equivalent Matroska container"""

import os
import re
import sys
import argparse
import datetime
import asyncio
import yaml

import numpy as np
import sounddevice as sd
import soundfile as sf
import queue
import logging
import tempfile
import json
import subprocess

from subprocess import check_output


logger = logging.getLogger(__name__)



#
# DEFINES / CONSTANT / GLOBALS
#
_ROOT_DIR = os.path.abspath(os.path.dirname(__file__))
_CMD_DIR = os.path.join(_ROOT_DIR, "../hrtf")
_AURALIS_DIR = os.path.join(_ROOT_DIR,"../auralysSpeaker")
_HRTF_DIR = os.path.join(_ROOT_DIR,"../hrtf")
_AUDIO_DIR = os.path.join(_ROOT_DIR,"./audio")
_VERSE_DIR=os.path.join(_ROOT_DIR, "../../verse")

_AURALYS_WAV_CHANNELS_COUNT = 22

#
# EXECUTABLES / EXTERNAL CMDs
#
_FFMPEG_EXE = "/usr/bin/ffmpeg"
_FFPROBE_EXE = "/usr/bin/ffprobe"
_APLAY_EXE = "/usr/bin/aplay"

########################################################################################################################
#  DO NOT MODIFY CODE BELOW THIS LINE
########################################################################################################################

def int_or_str(text):
    """Helper function for argument parsing."""
    try:
        return int(text)
    except ValueError:
        return text

def getMediaInfo(filename, print_result=True):
    """
    Returns:
        result = dict with audio info where:
        result['format'] contains dict of tags, bit rate etc.
        result['streams'] contains a dict per stream with sample rate, channels etc.
    """
    result = check_output(
        [_FFPROBE_EXE, "-hide_banner", "-loglevel", "panic", "-show_format", "-show_streams", "-of", "json", filename]
    )

    result = json.loads(result)

    if print_result:
        print("\nFormat")

        for key, value in result["format"].items():
            print("   ", key, ":", value)

        print("\nStreams")
        for stream in result["streams"]:
            for key, value in stream.items():
                print("   ", key, ":", value)

        print("\n")

    return result

def extract_track(audio_in, track_num, audio_out):
    """
    Extract a specific audio track from a WAV file into a WAV file using ffmpeg.
    - mkv_path: path to the .mkv file
    - track_num: integer track index (0-based)
    - out_wav: path where the extracted WAV will be saved
    """
    cmd = [
        _FFMPEG_EXE, "-y",              # overwrite without asking
        "-i", audio_in,                 # input file
        "-map_channel", f"0.0.{track_num}",       # select track number
        "-acodec", "pcm_s24le",      # uncompressed PCM 24-bit
        audio_out
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return

def audiomux_wav_to_mkv(file_path=None, file_name=None, mux_pattern=[2,[14,15],[16,17],[18,19],[20,21]]):
    """
    remux the multi-track audio file into MKV
    with specific pattern
    """

    # load file
    in_filename = os.path.join(file_path, file_name+".wav")

    data_info =getMediaInfo(in_filename, print_result=False)

    if (_AURALYS_WAV_CHANNELS_COUNT != data_info["streams"][0]["channels"]):
        logger.error("not an Auralys wav file, skipping {}/{}".format(file_path,file_name))
        return -1

    logger.info("DE-MUXING {}".format(in_filename))

    print("DE-MUXING {}".format(in_filename))


    with tempfile.TemporaryDirectory() as tmpdir:
        #for idx in np.arange(data_info["streams"][0]["channels"]):
        for idx in [2,14,15,16,17,18,19,20,21]:

            out_filename=os.path.join(tmpdir, file_name+"_"+str(idx)+".wav"  )
            logger.info("EXTRACT {} TO: {}".format(idx,out_filename))
            extract_track(audio_in=in_filename, track_num=idx, audio_out=out_filename)

        # #######################################################################
        # ToDo: remove this hardcoded muxing patter and use the input mux_pattern
        # #######################################################################

        in_filename = os.path.join(file_path, file_name+".mkv")

        logger.info("MUXING {}".format(in_filename))

        # mono-to-stereo :binaural
        file_L=os.path.join(tmpdir, file_name+"_"+str(14))+".wav"
        file_R=os.path.join(tmpdir, file_name+"_"+str(15))+".wav"
        file_out=os.path.join(tmpdir, file_name+"_binaural.wav")
        cmd=[_FFMPEG_EXE,"-y","-loglevel","error","-stats","-i",str(file_L),"-i",str(file_R),"-filter_complex","\"[0:a][1:a]join=inputs=2:channel_layout=stereo[aout]\"", "-map \"[aout]\"","-acodec","pcm_s24le",str(file_out)," > /dev/null 2>&1"]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        os.system(" ".join(cmd))

        # mono-to-stereo :array_six_front
        file_L=os.path.join(tmpdir, file_name+"_"+str(16))+".wav"
        file_R=os.path.join(tmpdir, file_name+"_"+str(17))+".wav"
        file_out=os.path.join(tmpdir, file_name+"_array_six_front.wav")
        cmd=[_FFMPEG_EXE,"-y","-loglevel","error","-stats","-i",str(file_L),"-i",str(file_R),"-filter_complex","\"[0:a][1:a]join=inputs=2:channel_layout=stereo[aout]\"", "-map \"[aout]\"","-acodec","pcm_s24le",str(file_out)," > /dev/null 2>&1"]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)        
        os.system(" ".join(cmd))

        # mono-to-stereo :array_six_middle
        file_L=os.path.join(tmpdir, file_name+"_"+str(18))+".wav"
        file_R=os.path.join(tmpdir, file_name+"_"+str(19))+".wav"
        file_out=os.path.join(tmpdir, file_name+"_array_six_middle.wav")
        cmd=[_FFMPEG_EXE,"-y","-loglevel","error","-stats","-i",str(file_L),"-i",str(file_R),"-filter_complex","\"[0:a][1:a]join=inputs=2:channel_layout=stereo[aout]\"", "-map \"[aout]\"","-acodec","pcm_s24le",str(file_out)," > /dev/null 2>&1"]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)        
        os.system(" ".join(cmd))

        # mono-to-stereo :array_six_rear
        file_L=os.path.join(tmpdir, file_name+"_"+str(20))+".wav"
        file_R=os.path.join(tmpdir, file_name+"_"+str(21))+".wav"
        file_out=os.path.join(tmpdir, file_name+"_array_six_rear.wav")
        cmd=[_FFMPEG_EXE,"-y","-loglevel","error","-stats","-i",str(file_L),"-i",str(file_R),"-filter_complex","\"[0:a][1:a]join=inputs=2:channel_layout=stereo[aout]\"", "-map \"[aout]\"","-acodec","pcm_s24le",str(file_out)," > /dev/null 2>&1"]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)        
        os.system(" ".join(cmd))

        logger.info("MUXING MKV {}".format(in_filename))
        file_in=os.path.join(tmpdir, file_name+"_"+str(2)+".wav")
        file_out= os.path.join(file_path, file_name+".mkv")
        cmd=[_FFMPEG_EXE,"-y","-loglevel","error","-stats",
            "-i", str(file_in),
            "-i",str(os.path.join(tmpdir, file_name+"_binaural.wav")),
            "-i",str(os.path.join(tmpdir, file_name+"_array_six_front.wav")),
            "-i",str(os.path.join(tmpdir, file_name+"_array_six_middle.wav")),
            "-i",str(os.path.join(tmpdir, file_name+"_array_six_rear.wav")),
            "-map","0:a",
            "-map","1:a",
            "-map","2:a",
            "-map","3:a",
            "-map","4:a",
            "-metadata:s:a:0","title=\"input\"",
            "-metadata:s:a:2","title=\"binaural\"",
            "-metadata:s:a:3","title=\"array_six_front\"",
            "-metadata:s:a:4","title=\"array_six_middle\"",
            "-metadata:s:a:5","title=\"array_six_rear\"",
            "-movflags",
            "+faststart",
            "-acodec","copy",
            str(file_out)
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)        

        if(os.path.isfile(file_out)):
            logger.info("MUXING DONE. MKV {}".format(in_filename))
        else:
            logger.error("MUXING FAILED. MKV {}".format(in_filename))

    return 0

def find_files_with_regex(file_path, file_name_pattern):
    """
    Search recursively in 'file_path' for files whose names match the given regex pattern.
    
    Args:
        file_path (str): The starting directory to search in.
        file_name_pattern (str): A regex pattern to match filenames (not full paths).
        
    Returns:
        list[str]: List of absolute paths to matching files.
    """
    matches = []
    pattern = re.compile(file_name_pattern)

    for root, dirs, files in os.walk(file_path):
        for filename in files:
            if pattern.search(filename):
                matches.append(os.path.abspath(os.path.join(root, filename)))

    return matches


def audiomux_files(path):
    auralys_wav_list=[]

    wav_list = find_files_with_regex(path, "_0.wav")

    if(len(wav_list)>0):
        for f in wav_list:
            f_info = getMediaInfo(f, print_result=False)
            if(_AURALYS_WAV_CHANNELS_COUNT == f_info["streams"][0]["channels"]):
                auralys_wav_list.append(f)

    if(len(auralys_wav_list)>0):
        # mux them all
        for f in auralys_wav_list:
            f_path = os.path.dirname(f)
            f_name = os.path.splitext(os.path.basename(f))[0]
            audiomux_wav_to_mkv(file_path=f_path, file_name=f_name)



def run_main(args):

    if os.path.isdir(args.input):
        print("FOLDER")

        audiomux_files(args.input)

    if os.path.isfile(args.input):
        print("FILE")


#
# MAIN
#
if __name__ == "__main__":
    parser = argparse.ArgumentParser(add_help=False)

    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, parents=[parser]
    )
    parser.add_argument(
        "-i",
        "--input",
        type=str,
        required=True,
        default="./audio.wav",
        help="input file or folder (default: %(default)s)",
    )
    parser.add_argument(
        "-r",
        "--remove",
        type=bool,
        required=False,
        default=False,
        help="remove original files after mux (default: %(default)s)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        default=False,
        help="verbose (default: %(default)s)",
    )

    args, remaining = parser.parse_known_args()

    #
    # set debug verbosity
    #
    if args.verbose:
        logging.basicConfig(level=logging.INFO)
    else:
        logging.basicConfig(level=logging.WARNING)

    #
    # setup log
    #
    # logger.info("-" * 80)
    # logger.info("SETUP:")
    # logger.info("-" * 80)
    # for p in yaml_params:
    #     logger.info("{} : {}".format(str(p), str(yaml_params[p])))

    #
    run_main(args)