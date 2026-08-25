"""
Compares static vs dynamic task decomposition on the real, unevenly-
sized test dataset, reports whether dynamic load-balancing actually
won, and measures the CONVOY EFFECT in the static case - the exact
FCFS phenomenon from lecture ('short process behind long process'),
here appearing as idle worker capacity stuck behind one long-running
static chunk.
"""


import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# ^ lets this test import project modules (compressor.py etc.) regardless of
# where it's run from, now that test files live in their own tests/ folder

import os
from compressor import list_files
from decomposition import run_static_decomposition, run_dynamic_decomposition, compute_convoy_gap

TEST_FOLDER = os.path.expanduser("~/parallel-compressor/testdata")
WORKERS = 4

if __name__ == "__main__":
    files = list_files(TEST_FOLDER)
    print(f"Testing with {len(files)} real files across {WORKERS} workers.\n")

    print("=== STATIC partitioning (fixed chunks, assigned up front) ===")
    static_duration, _, worker_finish_times = run_static_decomposition(files, WORKERS)
    print(f"Total time: {static_duration:.3f}s")

    fastest_id, fastest_time, slowest_id, slowest_time, gap = compute_convoy_gap(worker_finish_times)
    print(f"Worker finish times: {worker_finish_times}")
    print(f"CONVOY EFFECT: worker {fastest_id} finished at {fastest_time:.3f}s and then sat idle, "
          f"while worker {slowest_id} (stuck behind larger files in its fixed chunk) didn't "
          f"finish until {slowest_time:.3f}s - a {gap:.3f}s gap of wasted idle capacity, "
          f"the same 'short process behind long process' symptom described in the FCFS "
          f"lecture example, here caused by rigid static assignment instead of queue order.\n")

    print("=== DYNAMIC partitioning (shared queue, pulled on demand) ===")
    dynamic_duration, _, files_per_worker = run_dynamic_decomposition(files, WORKERS)
    print(f"Total time: {dynamic_duration:.3f}s")
    print(f"Files handled per worker: {files_per_worker}")
    print(f"  -> spread: min {min(files_per_worker.values())}, max {max(files_per_worker.values())} "
          f"(dynamic assignment naturally compensates for uneven file sizes, "
          f"which is exactly why the convoy effect above doesn't occur here)\n")

    faster = "DYNAMIC" if dynamic_duration < static_duration else "STATIC"
    print(f"Faster on this run: {faster} ({abs(static_duration - dynamic_duration):.3f}s difference)")