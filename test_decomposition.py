"""
Compares static vs dynamic task decomposition on the real, unevenly-
sized test dataset, and reports whether dynamic load-balancing
actually won on this machine, plus how evenly work ended up spread
across workers in the dynamic case.
"""

import os
from compressor import list_files
from decomposition import run_static_decomposition, run_dynamic_decomposition

TEST_FOLDER = os.path.expanduser("~/parallel-compressor/testdata")
WORKERS = 4

if __name__ == "__main__":
    files = list_files(TEST_FOLDER)
    print(f"Testing with {len(files)} real files across {WORKERS} workers.\n")

    print("=== STATIC partitioning (fixed chunks, assigned up front) ===")
    static_duration, _ = run_static_decomposition(files, WORKERS)
    print(f"Total time: {static_duration:.3f}s\n")

    print("=== DYNAMIC partitioning (shared queue, pulled on demand) ===")
    dynamic_duration, _, files_per_worker = run_dynamic_decomposition(files, WORKERS)
    print(f"Total time: {dynamic_duration:.3f}s")
    print(f"Files handled per worker: {files_per_worker}")
    print(f"  -> spread: min {min(files_per_worker.values())}, max {max(files_per_worker.values())} "
          f"(a large gap here would mean load was NOT evenly balanced)\n")

    faster = "DYNAMIC" if dynamic_duration < static_duration else "STATIC"
    print(f"Faster on this run: {faster} "
          f"({abs(static_duration - dynamic_duration):.3f}s difference)")