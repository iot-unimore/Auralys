#!/usr/bin/env python3
import h5py
import argparse

def print_data_delay(sofa_file):
    """
    Print all Data.Delay values from a SOFA file, one per line.
    """
    with h5py.File(sofa_file, "r") as f:

        # print("====================")
        # print("SOFA fields in file:")
        # print("====================")
        # for x in f:
        #     print(x)
        # print("====================\n")

        if "Data.Delay" in f:
            delays = f["Data.Delay"][:]  # usually shape (M, R)
            # print(f"Data.Delay shape: {delays.shape}\n")
            
            position = f["SourcePosition"]
            # print(f"SourcePosition shape: {position.shape}\n")

            # Iterate over measurements and receivers
            for m in range(delays.shape[0]):
                print(f"\n{m},{position[m][0]},{position[m][1]},{position[m][2]}", end="")
                for r in range(delays.shape[1]):
                    print(f",{delays[m, r]:3.0f}", end="")
        else:
            print("No Data.Delay field in this SOFA file.")

def main():
    parser = argparse.ArgumentParser(
        description="Print Data.Delay values from a SOFA file (one per line)."
    )
    parser.add_argument("sofa_file", help="Path to the .sofa file")
    args = parser.parse_args()
    print_data_delay(args.sofa_file)

if __name__ == "__main__":
    main()
