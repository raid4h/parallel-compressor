"""
Core primitive: compress ONE real file using a genuine fork()+exec()+wait()
sequence, implemented directly rather than through a higher-level Python wrapper.

IMPORTANT SAFETY NOTE ON fork() INSIDE A MULTI-THREADED / GUI PROGRAM:
POSIX fork() only duplicates the CALLING thread into the child - any
OTHER threads (including a GUI toolkit's internal threads/locks) simply
vanish in the child, potentially leaving internal state inconsistent.
The standard, safe pattern is: the child must do NOTHING except
immediately call exec() (or exit if exec fails) - no further Python-level
work, no touching the GUI, no logging through shared objects. The moment
exec() succeeds, the process is no longer running Python at all - it's
now running gzip - so any inconsistency from the fork itself becomes
irrelevant. Every function below follows this rule strictly.
"""

import os
import time


def list_files(folder_path):
    """
    Returns full paths of every REAL file directly inside folder_path,
    excluding subfolders and excluding any file that's already a .gz
    (so re-running this script doesn't try to compress its own output).
    """
    paths = []
    for name in os.listdir(folder_path):
        full_path = os.path.join(folder_path, name)
        if os.path.isfile(full_path) and not name.endswith(".gz"):
            paths.append(full_path)
    return paths


def compress_one_file(path):
    """
    Compresses ONE real file by:
      1. fork()  - create a new OS process, an exact duplicate of this one
      2. exec()  - inside the CHILD ONLY, replace its entire process image
                   with the real 'gzip' program
      3. wait()  - inside the PARENT ONLY, block until that specific child
                   process finishes, and retrieve its exit status

    Returns (success: bool, elapsed_seconds: float).
    """
    start = time.time()

    # fork() returns TWICE - once in each process it creates:
    #   - In the PARENT, it returns the new child's process ID (a
    #     positive integer).
    #   - In the CHILD, it returns exactly 0.
    # This return value is the ONLY way to tell which process you're
    # now running as, since both processes continue executing from
    # this exact line onward with otherwise identical memory.
    pid = os.fork()

    if pid == 0:
        # ---- THIS CODE RUNS ONLY IN THE CHILD PROCESS ----
        try:
            # os.execvp() REPLACES this child's entire process image
            # with the 'gzip' program. If this call succeeds, none of
            # the code after it ever runs - the process literally
            # becomes gzip. Flags used:
            #   -f  force: overwrite any existing .gz file from a
            #       previous run of this script
            #   -k  keep: don't delete the original file after
            #       compressing (so we can re-run benchmarks repeatedly)
            os.execvp("gzip", ["gzip", "-f", "-k", path])
        except Exception:
            # If gzip isn't found or exec itself fails for some other
            # reason, we must NOT let this child fall through and
            # continue running as if it were a normal continuation of
            # the parent - that would mean two Python processes both
            # running the rest of this program. os._exit() terminates
            # the child IMMEDIATELY, bypassing normal Python cleanup
            # (which is correct here - the child never finished
            # setting up as a real Python program instance).
            os._exit(1)

    else:
        # ---- THIS CODE RUNS ONLY IN THE PARENT PROCESS ----
        # os.waitpid(pid, 0) blocks the PARENT until the specific
        # child identified by 'pid' finishes, then returns its exit
        # status - this is the real system call that reaps a finished
        # child and prevents it from becoming a "zombie" process.
        _, status = os.waitpid(pid, 0)

        # os.WIFEXITED(status) checks the child terminated normally
        # (not via a crash/signal). os.WEXITSTATUS(status) extracts
        # its actual exit code - 0 conventionally means success.
        success = os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0

        elapsed = time.time() - start
        return success, elapsed

import threading
import subprocess


def compress_sequential(file_paths, event_queue=None):
    """
    BASELINE: compresses every file ONE AT A TIME, each via its own
    fork()+exec()+wait() cycle, with no overlap between files at all.
    """
    start = time.time()
    results = []

    for path in file_paths:
        success, elapsed = compress_one_file(path)
        results.append((path, success, elapsed))
        if event_queue:
            event_queue.put({"type": "file_done", "mode": "sequential", "path": path,
                              "success": success, "elapsed": elapsed})

    total_duration = time.time() - start
    return total_duration, results


def compress_concurrent_fork(file_paths, max_workers, event_queue=None):
    """
    Compresses every file using a BOUNDED POOL of concurrent child
    processes, each created via the SAME raw fork()+exec()+wait()
    sequence as compress_one_file(). One Python THREAD is spawned per
    file, but a real threading.Semaphore(max_workers) limits how many
    of those threads may be actively inside their fork()+wait() cycle
    (i.e., actually running a child process) at any one moment - this
    is genuine, meaningful synchronization: it prevents the system
    from being flooded with more concurrent gzip processes than
    intended, exactly like the -j flag on real build tools such as
    `make -j4`.
    """
    start = time.time()
    semaphore = threading.Semaphore(max_workers)
    results = []
    # Protects the shared 'results' list, since multiple worker
    # threads append to it concurrently once their file finishes.
    results_lock = threading.Lock()

    def worker(path):
        semaphore.acquire()  # blocks here once max_workers children are already running
        try:
            success, elapsed = compress_one_file(path)  # real fork()+exec()+wait()
            with results_lock:
                results.append((path, success, elapsed))
            if event_queue:
                event_queue.put({"type": "file_done", "mode": "fork_pool", "path": path,
                                  "success": success, "elapsed": elapsed})
        finally:
            # 'finally' guarantees the semaphore is released even if
            # compress_one_file() raised an unexpected exception -
            # otherwise a single failure could permanently reduce the
            # pool's effective capacity for the rest of the run.
            semaphore.release()

    threads = [threading.Thread(target=worker, args=(path,)) for path in file_paths]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    total_duration = time.time() - start
    return total_duration, results


def compress_concurrent_subprocess(file_paths, max_workers, event_queue=None):
    """
    Same goal as compress_concurrent_fork(), but using Python's
    subprocess module instead of raw os.fork()/os.execvp(). Included
    specifically as a comparison: subprocess.Popen() calls fork()+exec()
    INTERNALLY on Linux, so this measures the overhead of Python's
    convenience wrapper over the same underlying system calls, not a
    fundamentally different mechanism.

    Uses a shared queue.Queue as the work list, drained by a fixed
    pool of max_workers threads - the classic thread-pool pattern.
    """
    import queue

    start = time.time()
    work_queue = queue.Queue()
    for path in file_paths:
        work_queue.put(path)

    results = []
    results_lock = threading.Lock()

    def worker():
        while True:
            try:
                path = work_queue.get_nowait()
            except queue.Empty:
                return  # no files left - this worker thread is done

            file_start = time.time()
            # subprocess.Popen + .wait() is Python's higher-level
            # equivalent of fork()+exec()+waitpid() combined.
            proc = subprocess.Popen(["gzip", "-f", "-k", path])
            proc.wait()
            elapsed = time.time() - file_start
            success = proc.returncode == 0

            with results_lock:
                results.append((path, success, elapsed))
            if event_queue:
                event_queue.put({"type": "file_done", "mode": "subprocess_pool", "path": path,
                                  "success": success, "elapsed": elapsed})

    threads = [threading.Thread(target=worker) for _ in range(max_workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    total_duration = time.time() - start
    return total_duration, results