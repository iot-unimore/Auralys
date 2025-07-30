#!/usr/bin/env python3

import argparse
import os
import re
import pandas as pd
import matplotlib.pyplot as plt
import glob

def parse_args():
    parser = argparse.ArgumentParser(description="Plot delay vs azimuth from CSV files using glob or regex.")
    parser.add_argument(
        'pattern',
        help='File pattern (glob or regex, depending on --mode)'
    )
    parser.add_argument(
        '--mode',
        choices=['glob', 'regex'],
        default='regex',
        help='Choose file matching mode: glob (wildcards) or regex (default: regex)'
    )
    parser.add_argument(
        '--root',
        default='.',
        help='Root directory to search from in regex mode (default: current directory)'
    )
    parser.add_argument(
        '--save',
        metavar='OUTPUT.png',
        help='Save the plot to a PNG file instead of displaying it'
    )
    parser.add_argument(
        '--title',
        default='Delay vs Azimuth',
        help='Plot title (default: Delay vs Azimuth)'
    )
    return parser.parse_args()

def find_files_glob(pattern):
    return glob.glob(pattern, recursive=True)

def find_files_regex(root_dir, pattern):
    matched_files = []
    regex = re.compile(pattern)
    for dirpath, _, filenames in os.walk(root_dir):
        for filename in filenames:
            full_path = os.path.join(dirpath, filename)
            if regex.fullmatch(full_path):
                matched_files.append(full_path)
    return matched_files

def plot_data(files, title):
    plt.figure(figsize=(10, 6))  # <- FIXED line
    for file in files:
        try:
            df = pd.read_csv(file)
            plt.plot(df['azimuth'], df['delay'], label=os.path.basename(file))
        except Exception as e:
            print(f"⚠️ Failed to load {file}: {e}")
    plt.xlabel('Azimuth (degrees)')
    plt.ylabel('Delay')
    plt.title(title)
    plt.legend()
    plt.grid(True)
    plt.tight_layout()

def main():
    args = parse_args()

    if args.mode == 'glob':
        files = find_files_glob(args.pattern)
    else:
        files = find_files_regex(args.root, args.pattern)

    if not files:
        print(f"❌ No files matched the pattern using mode '{args.mode}'.")
        return

    print(f"✅ Matched {len(files)} file(s):")
    for f in files:
        print(f"  {f}")

    plot_data(files, args.title)

    if args.save:
        plt.savefig(args.save)
        print(f"💾 Plot saved to {args.save}")
    else:
        plt.show()

if __name__ == "__main__":
    main()
