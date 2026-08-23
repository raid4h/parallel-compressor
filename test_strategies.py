"""
Compares all three compression strategies on the same real files,
so we can confirm each one works correctly AND see a first rough
timing comparison, before building the GUI or the full benchmark sweep.
"""

import os
from compressor import list_files, compress_sequential, compress_concurrent_fork, compress_concurrent_subprocess

# Point this at a folder with several real files. Using this project's
# own folder works for now; for a more convincing benchmark later,
# a folder with more/larger files will show clearer differences.
TEST_FOLDER = os.path.expanduser("~/parallel-compressor")
WORKERS = 4

if __name__ == "__main__":
    files = list_files(TEST_FOLDER)
    print(f"Found {len(files)} file(s) to compress.\n")

    print("=== Sequential ===")
    duration, results = compress_sequential(files)
    print(f"Total time: {duration:.3f}s\n")

    print(f"=== Fork Pool ({WORKERS} workers) ===")
    duration, results = compress_concurrent_fork(files, WORKERS)
    print(f"Total time: {duration:.3f}s\n")

    print(f"=== Subprocess Thread Pool ({WORKERS} workers) ===")
    duration, results = compress_concurrent_subprocess(files, WORKERS)
    print(f"Total time: {duration:.3f}s\n")

    print("Done. Compare the three total times above.")