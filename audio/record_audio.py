#!/usr/bin/env python3
"""playback & record with yaml descriptor"""

import os
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
AUDIO_CONFIG_SYNTAX_NAME = "audio_recording"
AUDIO_CONFIG_SYNTAX_VERSION_MIN = 0.1

_ROOT_DIR = os.path.abspath(os.path.dirname(__file__))
_CMD_DIR = os.path.join(_ROOT_DIR, "../hrtf")
_AURALIS_DIR = os.path.join(_ROOT_DIR,"../auralysSpeaker")
_HRTF_DIR = os.path.join(_ROOT_DIR,"../hrtf")
_AUDIO_DIR = os.path.join(_ROOT_DIR,"./audio")
_VERSE_DIR=os.path.join(_ROOT_DIR, "../../verse")

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

def audio_resample(infile, outfile, samplerate):
    cmd = [
        _FFMPEG_EXE,
        "-y",
        "-loglevel",
        "error",
        "-stats",
        "-i",
        str(infile),
        "-ar",
        str(samplerate),
        str(outfile),
        " > /dev/null 2>&1",
    ]

    logger.info("Running ffmpeg command:")
    logger.info(" ".join(cmd))
    os.system(" ".join(cmd))
    return


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

    logger.info("DE-MUXING {}".format(in_filename))

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

    return


async def play_silence(
    event=None,
    device=None,
    verbose=False,
    samplerate=96000,
    playback_amplitude=0.1,
    playback_duration=15,
    playback_beep=3,
    cli=False,
    **kwargs,
):
    loop = asyncio.get_event_loop()

    start_idx = 0

    def silence_callback(outdata, frames, time, status) -> None:
        nonlocal start_idx
        nonlocal samplerate
        nonlocal playback_duration
        nonlocal playback_beep
        nonlocal verbose
        nonlocal event

        if status:
            logger.debug(status, file=sys.stderr)

        # exp sweep Parameters
        T = playback_duration
        fs = samplerate

        if (start_idx + frames) > (T * fs):
            loop.call_soon_threadsafe(event.set)
            raise sd.CallbackStop()
            return None

        outdata[:] = np.zeros((frames, 1))

        # return silence OR beep to activate RME output
        if (start_idx + frames) < (playback_beep * fs):
            t = (start_idx + np.arange(frames)) / samplerate
            t = t.reshape(-1, 1)
            # fading sine beep
            outdata[:] = (playback_amplitude / 2) * np.sin((2 * np.pi * 1000) * t)

        start_idx += frames

    try:
        # samplerate = sd.query_devices(args.device, "output")["default_samplerate"]

        logger.info("duration:         [s]: " + str(playback_duration))
        logger.info("sampling rate    [Hz]: " + str(samplerate))

        # SANITY CHECK: verify audio recording format capabilities
        try:
            sd.check_output_settings(device=device, samplerate=samplerate)
        except:
            logger.error("unsupported audio playback format {}".format(samplerate))

        try:
            sd.check_output_settings(device=device, samplerate=48000)
        except:
            logger.error("unsupported audio playback format 48k")

        # playback stream
        stream = sd.OutputStream(device=device, channels=1, samplerate=samplerate, callback=silence_callback, **kwargs)

        with stream:
            if cli:
                print("#" * 80)
                print("praudio CTRL-C to stop playback")
                print("#" * 80)
            await event.wait()

    except KeyboardInterrupt:
        parser.exit("")

    except Exception as e:
        parser.exit(type(e).__name__ + ": " + str(e))

    logger.info("play_silence. done.")


async def play_audio(
    event=None,
    device=None,
    verbose=False,
    data=None,    
    playback_amplitude=1.0,
    samplerate=96000,
    # frequency_begin=20,
    # frequency_end=20000,
    playback_duration=15,
    playback_prepadding=2,
    playback_postpadding=2,
    playback_beep=0,
    cli=False,
    **kwargs,
):
    loop = asyncio.get_event_loop()
    # event = asyncio.Event()

    start_idx = 0

    def audio_callback(outdata, frames, time, status) -> None:
        nonlocal start_idx
        nonlocal samplerate
        nonlocal playback_amplitude
        # nonlocal frequency_begin
        # nonlocal frequency_end
        nonlocal playback_duration
        nonlocal playback_prepadding
        nonlocal playback_postpadding
        nonlocal playback_beep
        nonlocal verbose
        nonlocal event

        if status:
            logger.debug(status, file=sys.stderr)

        # exp sweep Parameters
        # f1 = frequency_begin
        # f2 = frequency_end
        fs = samplerate
        # duration and zero padding
        P_pre = int(playback_prepadding)
        P_post = int(playback_postpadding)
        T = playback_duration

        # compute pre/post padding idx in samples count
        P_pre_idx = int(P_pre * fs)
        P_post_idx = int((P_pre + T) * fs)

        # prepare empty chunk
        outdata[:] = np.zeros((frames, 1))

        # early exit on end of stream (pre+duration+post)
        # if (start_idx + frames) > (P_pre * fs + T * fs + P_post * fs):
        if (start_idx) > (P_pre * fs + T * fs + P_post * fs):
            loop.call_soon_threadsafe(event.set)
            raise sd.CallbackStop()
            return None

        # return silence OR beep to activate RME output
        if (start_idx + frames) < (P_pre_idx):
            if (start_idx + frames) < (playback_beep * fs):
                t = (start_idx + np.arange(frames)) / samplerate
                t = t.reshape(-1, 1)
                # fading sine beep
                outdata[:] = (playback_amplitude / 2) * np.sin((2 * np.pi * 1000) * t)

        # return silence OR audio (or a mix of both)
        if (start_idx + frames) > (P_pre_idx):
            if start_idx > P_pre_idx:
                frames_audio = frames
                start_audio_idx = start_idx - P_pre_idx
            else:
                frames_audio = (start_idx + frames) - P_pre_idx
                start_audio_idx = 0 #P_pre_idx
 
            # copy audio from source: handle tails across pre/post padding
            if(start_audio_idx < len(data)):
                if((start_audio_idx+frames_audio) < len(data)):
                    outdata[(frames - frames_audio) :] = playback_amplitude * data[(start_audio_idx) : (start_audio_idx +frames_audio)]
                else:
                    frames_audio = len(data) - start_audio_idx
                    outdata[:frames_audio] = playback_amplitude * data[start_audio_idx : ]

            # set to zero extra samples
            if (start_idx + frames) > (P_post_idx):
                if start_idx < P_post_idx:
                    outdata[(P_post_idx - start_idx) :] = 0
                else:
                    outdata[:] = 0

        start_idx += frames

    try:
        # samplerate = sd.query_devices(args.device, "output")["default_samplerate"]

        # logger.info("frequency_begin  [Hz]: " + str(frequency_begin))
        # logger.info("frequency_end    [Hz]: " + str(frequency_end))
        logger.info("duration:         [s]: " + str(playback_duration))
        logger.info("amplitude            : " + str(playback_amplitude))
        logger.info("sampling rate    [Hz]: " + str(samplerate))

        # SANITY CHECK: verify audio recording format capabilities
        try:
            sd.check_output_settings(device=device, samplerate=samplerate)
        except:
            logger.error("unsupported audio playback format {}".format(samplerate))

        try:
            sd.check_output_settings(device=device, samplerate=48000)
        except:
            logger.error("unsupported audio playback format 48k")

        # playback stream
        stream = sd.OutputStream(device=device, channels=1, samplerate=samplerate, callback=audio_callback, **kwargs)

        with stream:
            if cli:
                print("#" * 80)
                print("praudio CTRL-C to stop playback")
                print("#" * 80)
            await event.wait()

    except KeyboardInterrupt:
        parser.exit("")

    except Exception as e:
        parser.exit(type(e).__name__ + ": " + str(e))

    logger.info("play_audio. done.")


async def record_audio(
    event=None,
    device=None,
    verbose=False,
    samplerate=96000,
    playback_duration=0,
    playback_repeat=1,
    measure_folder="./",
    measure_name="audio",
    cli=False,
    **kwargs,
):
    loop = asyncio.get_event_loop()
    # q = queue.Queue()
    audio_file = None

    def record_callback(indata, frames, time, status):
        """This is called (from a separate thread) for each audio block."""
        if status:
            logger.debug(status, file=sys.stderr)

        audio_file.write(indata.copy())

    try:
        try:
            audio_file = sf.SoundFile(
                measure_folder + "/" + measure_name + "/audio_" + str(playback_repeat) + ".wav",
                mode="w",
                samplerate=96000,
                channels=22,
                subtype="PCM_24",
            )
        except:
            logger.error("cannot open audio file for write")

        try:
            sd.check_input_settings(device=device, samplerate=samplerate)
        except:
            logger.error("unsupported audio recording format")

        # stream = sd.InputStream(samplerate=samplerate, device=device, channels=4, callback=record_callback)
        stream = sd.InputStream(samplerate=samplerate, device=device, channels=22, callback=record_callback)

        with stream:
            if cli:
                print("#" * 80)
                print("praudio Ctrl+C to stop recording")
                print("#" * 80)
            await event.wait()

            # while True:
            #    file.write(q.get())

        audio_file.close()

    except KeyboardInterrupt:
        parser.exit("")

    except Exception as e:
        parser.exit(type(e).__name__ + ": " + str(e))

    logger.info("record_audio. done.")


#
# ASYNCIO - MAIN
#
async def playrecord(cli=False, **kwargs):
    event = asyncio.Event()

    # preamble with silence for RME sync
    event.clear()
    asyncio.gather(
        record_audio(
            event=event,
            device=kwargs["input_device"],
            playback_repeat=99,
            measure_folder=kwargs["measure_folder"],
            measure_name=kwargs["measure_name"],
            cli=cli,
        ),
        play_silence(
            event=event,
            verbose=kwargs["verbose"],
            device=kwargs["output_device"],
            samplerate=kwargs["samplerate"],
            playback_amplitude=kwargs["playback_amplitude"],
            playback_duration=5,  # kwargs["playback_duration"],
            cli=cli,
        ),
    )
    await event.wait()

    for voice in kwargs["verseVoicesPlayList"]:

        logger.info(f"playing voice:{voice[0]}/{voice[1]}")

        info_file=os.path.join(_VERSE_DIR,"resources/voices",voice[0],"info",voice[1])+".yaml"

        audio_yaml = []
        try:
            with open(info_file, "r") as file:
                audio_yaml = yaml.safe_load(file)
        except:
            logger.error("cannot read audio info file {}".format(info_file))


        audio_file=os.path.join(_VERSE_DIR,"resources/voices",voice[0],audio_yaml["file"])

        # load file and convert to MONO if needed
        audio_data = []
        audio_samplerate = kwargs["samplerate"]
        if os.path.isfile(audio_file):
            try:
                audio_data, audio_samplerate = sf.read(audio_file, always_2d=True)
            except:
                logger.error("cannot read audio file {}".format(audio_file))

        # check for resampling
        if audio_samplerate != kwargs["samplerate"]:
            audio_resample_filename = "_".join(["rs",str(kwargs["samplerate"]),voice[0],voice[1],".wav"])
            audio_resample_file=os.path.join(kwargs["measure_folder"],audio_resample_filename)
            # resample
            if not (os.path.isfile(audio_resample_file)):
                audio_resample(audio_file, audio_resample_file, kwargs["samplerate"])
            # swap
            audio_file=audio_resample_file    

            # reload
            if os.path.isfile(audio_file):
                try:
                    audio_data, audio_samplerate = sf.read(audio_file, always_2d=True)
                except:
                    logger.error("cannot read audio file {}".format(audio_file))


        for r in range(kwargs["playback_repeat"]):
            event.clear()

            asyncio.gather(
                record_audio(
                    event=event,
                    device=kwargs["input_device"],
                    playback_repeat=r,
                    measure_folder=kwargs["measure_folder"],
                    measure_name=kwargs["measure_name"]+ "/" + voice[0] + "/" +voice[1],
                    cli=cli,
                ),
                play_audio(
                    event=event,
                    verbose=kwargs["verbose"],
                    device=kwargs["output_device"],
                    data=audio_data,
                    playback_amplitude=kwargs["playback_amplitude"],
                    samplerate=audio_samplerate,
                    # frequency_begin=kwargs["frequency_begin"],
                    # frequency_end=kwargs["frequency_end"],
                    playback_duration=len(audio_data)/audio_samplerate,
                    playback_postpadding=kwargs["playback_postpadding"],
                    playback_prepadding=kwargs["playback_prepadding"],
                    cli=cli,
                ),
            )

            await event.wait()

            #
            # re-mux to MKV format
            # audiomux_wav_to_mkv(file_path=kwargs["measure_folder"]+"/"+kwargs["measure_name"]+ "/" + voice[0] + "/" +voice[1], file_name="audio_" + str(r))


def run_main(**kwargs):
    # load and update config file for this recording saudioion
    audio_config = []

    if kwargs["audio_yaml_config"] != "":
        try:
            with open(kwargs["audio_yaml_config"], "r") as file:
                audio_config = yaml.safe_load(file)
        except:
            sys.exit("\n[ERROR] cannot open/parse yaml config file: {}".format(kwargs["audio_yaml_config"]))

    try:
        # update audio stimulus params
        audio_config["custom"]["stimulus"]["type"] = "voice"
        audio_config["custom"]["stimulus"]["voice"]["amplitude"]["value"] = kwargs["playback_amplitude"]
        audio_config["custom"]["stimulus"]["voice"]["repeat"]["value"] = kwargs["playback_repeat"]

        audio_config["custom"]["stimulus"]["voice"]["padding"]["pre"]["beep"] = 0
        audio_config["custom"]["stimulus"]["voice"]["padding"]["pre"]["value"] = kwargs["playback_prepadding"]
        audio_config["custom"]["stimulus"]["voice"]["padding"]["post"]["beep"] = 0
        audio_config["custom"]["stimulus"]["voice"]["padding"]["post"]["value"] = kwargs["playback_postpadding"]

        # update audio recording params
        audio_config["custom"]["recording"]["samplerate"] = kwargs["samplerate"]
        audio_config["custom"]["recording"]["format"] = "wav"
        audio_config["custom"]["recording"]["subformat"] = "PCM_24"
        audio_config["custom"]["recording"]["bit_depth"] = "s24be"

        # update file naming
        audio_config["custom"]["project_folder"] = kwargs["measure_folder"].split("/")[-1]
        audio_config["custom"]["audio_folder"] = kwargs["measure_name"]
        audio_config["custom"]["audio_filename"] = "audio_0"

        # update general section
        audio_config["general"]["date_modified"] = datetime.date.today()

        # add versePlaybackList
        audio_config["verseVoicesPlayList"]={}
        idx=0
        for voice in kwargs["verseVoicesPlayList"]:
            audio_config["verseVoicesPlayList"][idx]={}
            audio_config["verseVoicesPlayList"][idx]["type"]="voice"
            audio_config["verseVoicesPlayList"][idx]["subtype"]=voice[0]
            audio_config["verseVoicesPlayList"][idx]["info"]=voice[1]
            idx+=1

        # write output config
        try:
            os.makedirs(kwargs["measure_folder"] + "/" + kwargs["measure_name"] + "/", exist_ok=True)
        except:
            logger.error("[ERROR] cannot create {} folder".format(kwargs["measure_folder"] + kwargs["measure_name"]))

        with open(kwargs["measure_folder"] + "/" + kwargs["measure_name"] + "/config.yaml", "w") as file:
            yaml.dump(audio_config, file)

    except:
        sys.exit(
            "\n[ERROR] cannot write yaml config file: {}".format(
                kwargs["measure_folder"] + "/" + kwargs["measure_name"] + "/config.yaml"
            )
        )

    # prepare audio recording folders
    try:
        for voice in kwargs["verseVoicesPlayList"]:
             os.makedirs(kwargs["measure_folder"] + "/" + kwargs["measure_name"] + "/" + voice[0] + "/" +voice[1])
    except:
        sys.exit(
            "\n[ERROR] cannot create rcordings output folders."
        )

    # verify config files
    for voice in kwargs["verseVoicesPlayList"]:
        info_file=os.path.join(_VERSE_DIR,"resources/voices",voice[0],"info",voice[1])+".yaml"
        if (os.path.isfile(info_file)):
            try:
                with open(info_file, "r") as file:
                    tmp_yaml = []
                    tmp_yaml = yaml.safe_load(file)
            except:
                sys.exit(
                    "\n[ERROR] invalid yaml config file for {}.".format(voice)
                )
        else:
            sys.exit(
                "\n[ERROR] missing yaml config file for {}.".format(info_file)
            )

    # uncomment this line to run audio recording
    return asyncio.run(playrecord(**kwargs))


#
# MAIN
#
if __name__ == "__main__":
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("-l", "--list-devices", action="store_true", help="show list of audio devices and exit")

    args, remaining = parser.parse_known_args()

    #
    # check if we just want to list devices and quit
    #
    if args.list_devices:
        print(sd.query_devices())
        parser.exit(0)

    #
    # parse command line params with defaults values
    #
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, parents=[parser]
    )
    parser.add_argument(
        "-s",
        "--samplerate",
        type=int,
        default=96000,
        help="sampling rate in Hz (default: %(default)s)",
    )
    parser.add_argument(
        "-yc",
        "--audio_yaml_config",
        type=str,
        default="./audio_params.yaml",
        help="yaml config file (default: %(default)s)",
    )
    parser.add_argument(
        "-m",
        "--measure_folder",
        type=str,
        default="./",
        help="measure output folder (default: %(default)s)",
    )
    parser.add_argument(
        "-n",
        "--measure_name",
        type=str,
        default="audio",
        help="measure output name (default: %(default)s)",
    )

    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        default=False,
        help="verbose (default: %(default)s)",
    )

    parser.add_argument("-i", "--input_device", type=int_or_str, help="input device (numeric ID or substring)")
    parser.add_argument("-o", "--output_device", type=int_or_str, help="output device (numeric ID or substring)")
    parser.add_argument(
        "-aa", "--playback_amplitude", type=float, default=0.2, help="audio amplitude level(default: %(default)s)"
    )

    args = parser.parse_args(remaining)

    # set debug verbosity
    if args.verbose:
        logging.basicConfig(level=logging.INFO)
    else:
        logging.basicConfig(level=logging.WARNING)

    # load and update config file for this recording saudioion
    audio_config = []

    if args.audio_yaml_config != "":
        try:
            with open(args.audio_yaml_config, "r") as file:
                audio_config = yaml.safe_load(file)
        except:
            sys.exit("\n[ERROR] cannot open/parse yaml config file: {}".format(args.audio_yaml_config))

    try:
        #
        # update existing params
        #

        # stimulus
        audio_config["custom"]["stimulus"]["voice"]["padding"]["pre"]["beep"] = 0
        audio_config["custom"]["stimulus"]["voice"]["padding"]["pre"]["value"] = args.playback_prepadding
        audio_config["custom"]["stimulus"]["voice"]["padding"]["post"]["beep"] = 0
        audio_config["custom"]["stimulus"]["voice"]["padding"]["post"]["value"] = args.playback_postpadding
        audio_config["custom"]["stimulus"]["voice"]["amplitude"]["value"] = args.playback_amplitude

        # audio recording
        audio_config["custom"]["recording"]["samplerate"] = args.samplerate

        # write output config
        try:
            os.makedirs(args.measure_folder + "/" + args.measure_name + "/", exist_ok=False)
        except:
            logger.error("[ERROR] cannot create {} folder".format(args.measure_folder + args.measure_name))

        with open(args.measure_folder + "/" + args.measure_name + "/config.yaml", "w") as file:
            yaml.dump(audio_config, file)

    except:
        sys.exit(
            "\n[ERROR] cannot write yaml config file: {}".format(
                args.measure_folder + "/" + args.measure_name + "/config.yaml"
            )
        )

    try:
        asyncio.run(playrecord(cli=True, **vars(args)))

    except KeyboardInterrupt:
        sys.exit("\nInterrupted by user")
