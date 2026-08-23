"""
Explores CPU SCHEDULING at the process level: Linux's scheduler uses
each process's 'niceness' value (-20 to 19; LOWER = higher scheduling
priority) as one input when deciding which runnable process gets the
CPU next. os.nice() is a direct wrapper around the real nice()/
setpriority() system calls.

This experiment: run a batch of REAL gzip compressions at a LOWERED
priority (nice = 15, deliberately deprioritized) WHILE a separate,
CPU-heavy background load runs at NORMAL priority, and compare total
completion time against running that same batch at DEFAULT priority
under the same background load - a genuine, measurable demonstration
of how process priority affects real scheduling outcomes under
contention, not just a description of the concept.
"""

import os
import time
import threading

from compressor import compress_one_file


def _cpu_heavy_background_load(stop_event):
    """
    Runs on ordinary threads at DEFAULT priority, deliberately burning
    CPU cycles continuously, to create real contention for the
    scheduler to arbitrate between - without this, there'd be nothing
    for a lowered-priority process to actually compete against.
    """
    while not stop_event.is_set():
        _ = sum(i * i for i in range(10000))  # pure CPU-bound busywork, no real purpose beyond load


def compress_batch_with_priority(file_paths, niceness, event_queue=None):
    """
    Compresses file_paths sequentially, but FIRST lowers (or raises,
    if permitted) THIS process's scheduling priority via os.nice()
    before starting. Since child processes inherit their parent's
    niceness by default, every gzip child spawned via fork()+exec()
    from here also runs at this same lowered priority.
    """
    original_niceness = os.nice(0)  # os.nice(0) both applies a 0 change AND returns the CURRENT value

    if niceness != 0:
        # os.nice(n) INCREMENTS the current niceness by n and returns
        # the new value - it's relative, not absolute, hence starting
        # from a known baseline (0) matters for a fair comparison.
        os.nice(niceness)

    start = time.time()
    results = []
    for path in file_paths:
        success, elapsed = compress_one_file(path)
        results.append((path, success, elapsed))
        if event_queue:
            event_queue.put({
                "type": "priority_file_done", "niceness": niceness,
                "path": path, "elapsed": elapsed
            })
    duration = time.time() - start

    return duration, results


def run_priority_experiment(file_paths, background_threads, event_queue=None):
    """
    Runs the SAME batch of real files twice, under the SAME simulated
    CPU contention (a fixed number of CPU-heavy background threads at
    normal priority), once at default niceness and once deliberately
    lowered - isolating priority as the one variable that changed.
    """
    stop_event = threading.Event()
    load_threads = [threading.Thread(target=_cpu_heavy_background_load, args=(stop_event,))
                     for _ in range(background_threads)]
    for t in load_threads:
        t.start()

    try:
        if event_queue:
            event_queue.put({"type": "priority_phase", "phase": "default_priority_start"})
        default_duration, _ = compress_batch_with_priority(file_paths, niceness=0, event_queue=event_queue)

        if event_queue:
            event_queue.put({"type": "priority_phase", "phase": "low_priority_start"})
        # niceness=15 significantly deprioritizes this process relative
        # to the default-priority background load competing for CPU time.
        low_priority_duration, _ = compress_batch_with_priority(file_paths, niceness=15, event_queue=event_queue)
    finally:
        stop_event.set()  # ALWAYS stop the background load threads, even if compression raised an error
        for t in load_threads:
            t.join()

    if event_queue:
        event_queue.put({
            "type": "priority_done",
            "default_duration": default_duration,
            "low_priority_duration": low_priority_duration
        })

    return default_duration, low_priority_duration