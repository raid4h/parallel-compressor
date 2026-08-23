"""
Compares our hand-built strategies against Python's standard
concurrent.futures pool abstractions, on the same real files.
"""

import os
from compressor import list_files, compress_concurrent_fork, compress_concurrent_subprocess
from executor_compare import run_thread_pool_executor, run_process_pool_executor

TEST_FOLDER = os.path.expanduser("~/parallel-compressor/testdata")
WORKERS = 8

if __name__ == "__main__":
    files = list_files(TEST_FOLDER)
    print(f"Testing with {len(files)} real files, {WORKERS} workers.\n")

    print("=== Our hand-built fork() pool ===")
    duration, _ = compress_concurrent_fork(files, WORKERS)
    print(f"Time: {duration:.3f}s\n")

    print("=== Our hand-built subprocess thread pool ===")
    duration, _ = compress_concurrent_subprocess(files, WORKERS)
    print(f"Time: {duration:.3f}s\n")

    print("=== Standard library ThreadPoolExecutor ===")
    duration, _ = run_thread_pool_executor(files, WORKERS)
    print(f"Time: {duration:.3f}s\n")

    print("=== Standard library ProcessPoolExecutor ===")
    duration, _ = run_process_pool_executor(files, WORKERS)
    print(f"Time: {duration:.3f}s\n")

    print("Compare the four times above - they should be roughly similar, since "
          "they're all doing the same underlying work through different levels "
          "of abstraction over the same real system calls.")