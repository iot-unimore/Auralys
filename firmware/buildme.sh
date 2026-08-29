#!/usr/bin/env bash
# Compile-checks the auralysSpeaker sketch against the vendored copies of its
# external libraries under auralysSpeaker/libraries/, using the LOLIN S3 Mini
# board definition. Build output goes to build/, a throwaway folder excluded
# from git.
#
# The libraries/ folder is local only (see .gitignore): a fresh clone has to
# populate it before this script can build anything.
#
# Usage: ./buildme.sh [-v|-vv|-vvv] [--cdc-on-boot]
#   (no flag)  minimal: just arduino-cli's default size summary
#   -v         + progress echo (board, libraries, start/done markers)
#   -vv        + gcc warnings (--warnings all) and arduino-cli's own
#                processing log at info level (--log)
#   -vvv       + full compiler command verbose output (--verbose) and
#                arduino-cli's own log at trace level (--log-level trace)
#   --cdc-on-boot   set the board option CDCOnBoot=cdc (off/Disabled by
#                   default, matching the LOLIN S3 Mini's own default, where
#                   Serial is UART0 and not the USB CDC)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

ARDUINO_CLI="/home/gfilippi/bin/arduino-cli"
SKETCH="auralysSpeaker"
FQBN="esp32:esp32:lolin_s3_mini"

# the sketch uses FFat + OTA (FFat.h, esp_ota_ops.h, HTTPUpdate.h), so the
# partition table must be the ffat one: the board default is 4MB with spiffs,
# which builds fine but leaves the firmware without a FATFS partition
PARTITION_SCHEME="defaultffat"

# external libraries, vendored under the sketch folder. everything else
# (WiFi, HTTPClient, HTTPUpdate, Update, EEPROM, FS, FFat, esp_*, driver/*,
# soc/*, and the DNSServer/WebServer that WiFiManager pulls in) comes from
# the esp32 core and must NOT be shadowed by the older forks sitting in
# libraries/
LIBS_DIR="$SKETCH/libraries"
LIBS=(
    Adafruit_BusIO
    Adafruit_GFX_Library
    Adafruit_NeoPixel
    Adafruit_SH110X
    ArduinoJson
    CRC32
    ESP32Time
    LIS3DSH-master
    Time
    WiFiManager
)

usage()
{
    echo "usage: $0 [-v|-vv|-vvv] [--cdc-on-boot]" >&2
    echo "  (no flag)      minimal: just arduino-cli's default size summary" >&2
    echo "  -v             + progress echo (board, libraries, start/done markers)" >&2
    echo "  -vv            + gcc warnings and arduino-cli log (--warnings all --log)" >&2
    echo "  -vvv           + full compiler + trace-level arduino-cli log" >&2
    echo "  --cdc-on-boot  enable USB CDC On Boot (default: disabled)" >&2
    exit 1
}

VERBOSITY=0
CDC_ON_BOOT=0

for arg in "$@"; do
    case "$arg" in
        -v)             VERBOSITY=1 ;;
        -vv)            VERBOSITY=2 ;;
        -vvv)           VERBOSITY=3 ;;
        --cdc-on-boot)  CDC_ON_BOOT=1 ;;
        *)              usage ;;
    esac
done

if [[ ! -d "$LIBS_DIR" ]]; then
    echo "error: $LIBS_DIR not found. the vendored libraries are local only," >&2
    echo "       they are not committed: populate that folder first." >&2
    exit 1
fi

missing=()
for lib in "${LIBS[@]}"; do
    [[ -d "$LIBS_DIR/$lib" ]] || missing+=("$lib")
done

if (( ${#missing[@]} )); then
    echo "error: missing libraries under $LIBS_DIR: ${missing[*]}" >&2
    exit 1
fi

# Board options change what core.a gets compiled with (e.g. CDCOnBoot pulls
# in different USB/Serial glue). Reusing the same incremental build-path
# across different --board-options mixes stale object files from the other
# config and fails at link time (seen in practice: undefined references to
# i2cSetClock/digitalWrite/initArduino/...), so each option combination gets
# its own build subfolder instead of sharing one.
if (( CDC_ON_BOOT )); then
    BUILD_PATH="build/cdc-on-boot"
else
    BUILD_PATH="build/default"
fi

BOARD_OPTIONS="PartitionScheme=$PARTITION_SCHEME"

if (( CDC_ON_BOOT )); then
    BOARD_OPTIONS="$BOARD_OPTIONS,CDCOnBoot=cdc"
fi

CLI_ARGS=(-b "$FQBN" --build-path "$BUILD_PATH" --board-options "$BOARD_OPTIONS")
for lib in "${LIBS[@]}"; do
    CLI_ARGS+=(--library "$LIBS_DIR/$lib")
done

if (( VERBOSITY >= 2 )); then
    CLI_ARGS+=(--warnings all --log)
fi
if (( VERBOSITY >= 3 )); then
    CLI_ARGS+=(--verbose --log-level trace)
fi

if (( VERBOSITY >= 1 )); then
    echo "==> Compiling $SKETCH for $FQBN"
    echo "==> Libraries: ${LIBS[*]}"
    echo "==> arduino-cli: $ARDUINO_CLI"
    echo "==> Board options: $BOARD_OPTIONS"
    if (( CDC_ON_BOOT )); then
        echo "==> CDC on Boot: enabled"
    else
        echo "==> CDC on Boot: disabled (board default)"
    fi
    echo
fi

"$ARDUINO_CLI" compile "${CLI_ARGS[@]}" "$SKETCH"

if (( VERBOSITY >= 1 )); then
    echo
    echo "==> Build OK -> $BUILD_PATH/$SKETCH.ino.bin"
fi
