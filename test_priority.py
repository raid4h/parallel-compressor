"""
Runs the priority race 3 times and reports the MEDIAN, since a single
run isn't reliable evidence - system noise (especially inside a
virtualized environment like WSL2) can make individual trials swing
in either direction.
"""

import os
from compressor import list_files
from priority import run_priority_race

TEST_FOLDER = os.path.expanduser("~/parallel-compressor/testdata")

if __name__ == "__main__":
    files = list_files(TEST_FOLDER)
    cpu_cores = os.cpu_count()

    print(f"Testing with {len(files)} real files, {cpu_cores} background load threads, "
          f"3 repeats per priority group.\n")

    result = run_priority_race(files, background_threads=cpu_cores, repeats=3)

    print(f"Default priority (nice=0):   median {result['default_throughput']:.2f} files/sec  "
          f"(range: {min(result['all_default_throughputs']):.2f}-{max(result['all_default_throughputs']):.2f})")
    print(f"Lowered priority (nice=+15): median {result['lowered_throughput']:.2f} files/sec  "
          f"(range: {min(result['all_lowered_throughputs']):.2f}-{max(result['all_lowered_throughputs']):.2f})")

    default_tput = result["default_throughput"]
    lowered_tput = result["lowered_throughput"]

    if default_tput > lowered_tput:
        advantage = ((default_tput - lowered_tput) / lowered_tput) * 100
        print(f"\nDefault priority: {advantage:.1f}% higher median throughput across 3 trials.")
    else:
        disadvantage = ((lowered_tput - default_tput) / default_tput) * 100
        print(f"\nNo default-priority advantage across 3 trials (lowered priority was "
              f"{disadvantage:.1f}% higher) - the effect may be smaller than system noise "
              f"at this workload size, or masked by WSL2 virtualization scheduling.")