"""
Runs the worker-count sweep on real files and prints results,
including which worker count was empirically fastest on this machine.
"""

import os
from compressor import list_files
from benchmark import run_worker_sweep, find_optimal_worker_count

TEST_FOLDER = os.path.expanduser("~/parallel-compressor/testdata")

if __name__ == "__main__":
    files = list_files(TEST_FOLDER)
    print(f"Found {len(files)} file(s).\n")

    cpu_cores = os.cpu_count()
    print(f"This machine reports {cpu_cores} CPU cores (via os.cpu_count()).\n")

    # Sweep past the core count too, to show that piling on MORE
    # concurrent processes eventually stops helping (or hurts) once
    # you exceed available cores - the actual optimization insight.
    worker_counts = sorted(set([1, 2, 4, cpu_cores, cpu_cores * 2]))

    results = run_worker_sweep(files, worker_counts)

    print(f"{'Workers':<10}{'Time (s)':<12}{'Avg CPU %':<12}")
    for r in results:
        print(f"{r['workers']:<10}{r['duration']:<12.3f}{r['avg_cpu_utilization']:<12.1f}")

    best = find_optimal_worker_count(results)
    print(f"\nFastest configuration: {best['workers']} workers "
          f"({best['duration']:.3f}s, {best['avg_cpu_utilization']:.1f}% avg CPU utilization)")