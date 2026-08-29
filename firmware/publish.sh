#!/usr/bin/env bash
# Publishes the compiled auralysSpeaker OTA image
# (build/default/auralysSpeaker.ino.bin, see buildme.sh) to the update
# server: computes the same identity string httpUpdateCheck()
# (as_httpupdate.ino) builds into SwVer -
#   <codename>_<platform>_<cpu_arch>_<cpu_type>_<mjr>.<min>.<rev>_<build>
# - parsed from the sketch source rather than hardcoded (see define_value()
# below), then scp's the image to HTTP_SERVER renamed to
# "<identity string>.bin" under the fixed remote update-tree path (after
# chmod'ing the local file to 644). Prints the destination and asks for
# confirmation before copying; scp itself prompts for the piweb account's
# password interactively - no key-based auth is set up here on purpose.
#
# Usage: ./publish.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# every version/platform define lives in the main sketch file: this project
# has no separate version header
MAIN_INO="$SCRIPT_DIR/auralysSpeaker/auralysSpeaker.ino"
LOCAL_BIN="$SCRIPT_DIR/build/default/auralysSpeaker.ino.bin"

HTTP_SERVER="192.168.12.5"
HTTP_SERVER_USER="piweb"
REMOTE_DIR="/var/www/html/brws_iot/update/auralysS/brws/lolin"

# extracts the quoted or parenthesized value of a #define NAME from a file,
# e.g. `#define SW_VER_MJR (0) /* ... */` -> "0", `#define BRWS_SW_CODENAME "auralysS"` -> "auralysS".
# the trailing [[:space:]] in the pattern is what keeps BRWS_SW_CODENAME from
# matching the BRWS_SW_CODENAME_SIZE_MAX line defined just above it
define_value()
{
    local name="$1" file="$2"
    local line
    line="$(grep -m1 "^#define[[:space:]]\+${name}[[:space:]]" "$file")" || {
        echo "publish.sh: could not find #define ${name} in ${file}" >&2
        exit 1
    }
    sed -E 's/^#define[[:space:]]+[A-Za-z0-9_]+[[:space:]]+//; s/^\(([^)]*)\).*/\1/; s/^"([^"]*)".*/\1/' <<< "$line"
}

codename="$(define_value BRWS_SW_CODENAME "$MAIN_INO")"
platform="$(define_value BRWS_SW_PLATFORM "$MAIN_INO")"
cpu_arch="$(define_value BRWS_HW_CFG_CPU_ARCH "$MAIN_INO")"
cpu_type="$(define_value BRWS_HW_CFG_CPU_TYPE "$MAIN_INO")"
ver_mjr="$(define_value SW_VER_MJR "$MAIN_INO")"
ver_min="$(define_value SW_VER_MIN "$MAIN_INO")"
ver_rev="$(define_value SW_VER_REV "$MAIN_INO")"

# SW_VER_BUILD isn't a plain #define value - it's computed by the sketch's own
# DEBUG/QA preprocessor conditional (0=release, 1=debug, 2=release-qa,
# 3=debug-qa). Mirror that same two-flag logic here rather than grepping for
# "SW_VER_BUILD (N)" directly, since all 4 possible lines exist in the file and
# only the preprocessor knows which one is actually active.
# NOTE: the ^[[:space:]]*#define anchor is what makes a commented-out
# "//#define DEBUG" correctly count as not defined.
debug_defined=0
qa_defined=0
grep -qE '^[[:space:]]*#define[[:space:]]+DEBUG([[:space:]]|$)' "$MAIN_INO" && debug_defined=1
grep -qE '^[[:space:]]*#define[[:space:]]+QA([[:space:]]|$)' "$MAIN_INO" && qa_defined=1

if (( debug_defined )); then
    ver_build=$(( qa_defined ? 3 : 1 ))
else
    ver_build=$(( qa_defined ? 2 : 0 ))
fi

sw_ver="${codename}_${platform}_${cpu_arch}_${cpu_type}_${ver_mjr}.${ver_min}.${ver_rev}_${ver_build}"
remote_path="${REMOTE_DIR}/${sw_ver}.bin"

if [[ ! -f "$LOCAL_BIN" ]]; then
    echo "publish.sh: $LOCAL_BIN not found - run buildme.sh first" >&2
    exit 1
fi

echo "destination: ${HTTP_SERVER_USER}@${HTTP_SERVER}:${remote_path}"
read -r -p "Publish $(basename "$LOCAL_BIN") there? [y/N] " answer
if [[ "${answer,,}" != "y" ]]; then
    echo "aborted."
    exit 1
fi

chmod 644 "$LOCAL_BIN"
scp "$LOCAL_BIN" "${HTTP_SERVER_USER}@${HTTP_SERVER}:${remote_path}"
