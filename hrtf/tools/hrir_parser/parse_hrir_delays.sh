#!/bin/bash

LOGFILE=$1
OUTPUT_DIR="elevation_rx_tables"

# Create output directory
mkdir -p "$OUTPUT_DIR"

# Extract relevant fields and sort by elevation, rx, then azimuth
grep "IR delay" "$LOGFILE" | \
sed -E 's/.*source ([^,]+),([^,]+),([^,]+), rx ([^,]+),.*IR delay=([0-9.]+) \[ms\].*/\1,\2,\3,\4,\5/' | \
sort -t',' -k2,2n -k4,4n -k1,1n > /tmp/sorted_hrir_data.csv

# Process into per-elevation-rx files
awk -F',' -v outdir="$OUTPUT_DIR" '
BEGIN { header = "azimuth,elevation,distance,rx,delay" }
{
    elevation = $2
    rx = $4
    file = outdir "/elevation_" elevation "_rx_" rx ".csv"
    key = elevation "_" rx
    if (!(key in seen)) {
        print header > file
        seen[key] = 1
    }
    print $0 >> file
}' /tmp/sorted_hrir_data.csv

