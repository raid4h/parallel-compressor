"""
Runs the real bounded producer-consumer pipeline on the test dataset,
using a deliberately SMALL queue capacity so backpressure actually
kicks in and is visible/provable, not just theoretical.
"""


import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# ^ lets this test import project modules (compressor.py etc.) regardless of
# where it's run from, now that test files live in their own tests/ folder

import os
from pipeline import run_pipeline

TEST_FOLDER = os.path.expanduser("~/parallel-compressor/testdata")

if __name__ == "__main__":
    # A small maxsize (e.g. 5) relative to the 63 real files ensures
    # the producer WILL block on a full queue at least once during
    # this run - proving the bounded buffer's backpressure is real,
    # not just theoretically present but never actually triggered.
    duration, discovered, results = run_pipeline(TEST_FOLDER, num_consumers=4, queue_capacity=5)

    print(f"Discovered: {discovered} files")
    print(f"Processed: {len(results)} files")
    print(f"Total time: {duration:.3f}s")
    failed = [r for r in results if not r[1]]
    if failed:
        print(f"Failed: {len(failed)} files")
    else:
        print("All files compressed successfully.")