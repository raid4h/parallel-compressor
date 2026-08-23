"""
Compares our hand-built fork()+exec() pool against Python's STANDARD
LIBRARY pool abstractions (concurrent.futures), to show both: (a) we
understand how a pool is built from the ground up using real system
calls, and (b) we understand why/when the standard library's
convenience wrapper is worth using instead.

ThreadPoolExecutor here still launches real gzip processes via
subprocess (so it's directly comparable to our subprocess-based pool),
while ProcessPoolExecutor spawns genuine separate Python worker
processes that each call our own compress_one_file() function
directly - a different, heavier-weight kind of parallelism than
launching gzip as a subprocess.
"""

import time
import subprocess
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor

from compressor import compress_one_file


def _compress_via_subprocess(path):
    """Small helper so ThreadPoolExecutor.map() can call one
    function per file, same real gzip subprocess call as before."""
    start = time.time()
    proc = subprocess.Popen(["gzip", "-f", "-k", path])
    proc.wait()
    elapsed = time.time() - start
    return path, proc.returncode == 0, elapsed


def run_thread_pool_executor(file_paths, max_workers):
    """
    Python's standard high-level thread pool abstraction. Internally,
    it manages its own internal work queue and worker thread lifecycle
    for you - the same CONCEPT as our hand-built subprocess pool, but
    with the bookkeeping already written and tested by the standard
    library.
    """
    start = time.time()
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = list(executor.map(_compress_via_subprocess, file_paths))
    duration = time.time() - start
    return duration, results


def run_process_pool_executor(file_paths, max_workers):
    """
    Python's standard high-level PROCESS pool abstraction. Unlike our
    manual os.fork() calls (which duplicate this exact running
    process), ProcessPoolExecutor spawns entirely fresh Python
    interpreter processes up front and reuses them across many tasks -
    a different, more "managed" process model, worth comparing against
    the raw fork() approach for both correctness and overhead.
    """
    start = time.time()
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        results = list(executor.map(compress_one_file, file_paths))
    duration = time.time() - start
    return duration, results