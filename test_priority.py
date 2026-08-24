"""
Runs the CORRECTED, concurrent priority race: both priority groups
compete for the CPU at the same real moment, isolating priority as
the sole variable - mirrors Multilevel Queue Scheduling's foreground
(default priority) vs background (lowered priority) dynamic, using
the real Linux scheduler on genuine fork()'d work.
"""

import os
from compressor import list_files
from priority import run_priority_race

TEST_FOLDER = os.path.expanduser("~/parallel-compressor/testdata")

if __name__ == "__main__":
    files = list_files(TEST_FOLDER)
    cpu_cores = os.cpu_count()

    print(f"Testing with {len(files)} real files under artificial CPU contention "
          f"({cpu_cores} background load threads).\n")
    print("Racing two priority groups CONCURRENTLY (not sequentially, unlike the "
          "earlier flawed version) to properly isolate priority as the sole variable.\n")

    default_duration, lowered_duration, default_tput, lowered_tput = run_priority_race(
        files, background_threads=cpu_cores
    )

    print(f"Default priority (nice=0):    {default_duration:.3f}s, "
          f"{default_tput:.2f} files/sec")
    print(f"Lowered priority (nice=+15):  {lowered_duration:.3f}s, "
          f"{lowered_tput:.2f} files/sec")

    if default_tput > lowered_tput:
        advantage = ((default_tput - lowered_tput) / lowered_tput) * 100
        print(f"\nDefault priority achieved {advantage:.1f}% higher throughput than the "
              f"deliberately lowered-priority group - the scheduler genuinely favored it "
              f"under real, simultaneous CPU contention.")
    else:
        print(f"\nNo clear priority advantage observed - possible if background load "
              f"didn't fully saturate all {cpu_cores} cores at once. Worth re-running "
              f"a few times to check consistency.")