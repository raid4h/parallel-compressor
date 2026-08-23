"""
Runs the CPU scheduling / priority experiment standalone: compresses
the same real files under real CPU contention, once at default
priority and once deliberately deprioritized via os.nice(), and
reports the real difference this made.
"""

import os
from compressor import list_files
from priority import run_priority_experiment

TEST_FOLDER = os.path.expanduser("~/parallel-compressor/testdata")

if __name__ == "__main__":
    files = list_files(TEST_FOLDER)[:20]  # a subset keeps this experiment reasonably quick
    print(f"Testing with {len(files)} real files under artificial CPU contention.\n")

    cpu_cores = os.cpu_count()
    print(f"Spawning {cpu_cores} CPU-heavy background threads at DEFAULT priority "
          f"to create real contention.\n")

    default_duration, low_priority_duration = run_priority_experiment(files, background_threads=cpu_cores)

    print(f"Default priority (nice=0):    {default_duration:.3f}s")
    print(f"Lowered priority (nice=+15):  {low_priority_duration:.3f}s")

    if low_priority_duration > default_duration:
        slowdown = ((low_priority_duration - default_duration) / default_duration) * 100
        print(f"\nLowering priority made this batch {slowdown:.1f}% SLOWER under contention - "
              f"the Linux scheduler genuinely favored the default-priority background load "
              f"over our deprioritized compression work.")
    else:
        print(f"\nNo significant slowdown observed - this can happen if background load "
              f"didn't fully saturate all {cpu_cores} cores, or scheduler behavior varies "
              f"by system load at the time.")