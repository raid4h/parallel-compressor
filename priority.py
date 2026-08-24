"""
CPU SCHEDULING experiment, redesigned as a genuine CONCURRENT race
rather than two sequential batches (the original sequential design
was vulnerable to page-cache and CPU-frequency-ramp-up confounds
between the two runs, which produced a misleading result).

This mirrors MULTILEVEL QUEUE SCHEDULING (Ch.5): a 'foreground' group
of real jobs at default priority races against a 'background' group
at deliberately lowered priority, both competing for the SAME CPU
cores at the SAME time - not a simulated queue structure, but the
real Linux scheduler's actual priority-based CPU time allocation,
applied to genuine fork()+exec() work.

Linux-specific detail worth knowing: os.nice() affects the CALLING
THREAD specifically, not the whole process - Linux implements each
thread as its own independently-schedulable kernel task with its own
niceness. Every child process fork()'d from a given thread inherits
THAT thread's niceness at the moment of the fork() call.
"""

import os
import time
import threading

from compressor import compress_one_file


def _cpu_heavy_background_load(stop_event):
    """Ordinary threads at DEFAULT priority, deliberately burning CPU
    continuously, to create real system-wide contention throughout
    the entire race - without this, there'd be nothing for either
    priority group to actually compete against."""
    while not stop_event.is_set():
        _ = sum(i * i for i in range(10000))


def _priority_runner(file_paths, niceness, label, results, results_lock, event_queue):
    """
    Runs as ITS OWN dedicated thread. Sets THIS THREAD's niceness
    (affecting only this thread, per the Linux behavior noted above),
    then compresses its assigned files - every child process forked
    from here inherits this thread's niceness at fork() time.
    """
    if niceness != 0:
        os.nice(niceness)

    start = time.time()
    for path in file_paths:
        success, elapsed = compress_one_file(path)
        with results_lock:
            results.append((label, path, success, elapsed))
        if event_queue:
            event_queue.put({
                "type": "priority_file_done", "group": label,
                "path": path, "elapsed": elapsed
            })
    duration = time.time() - start
    return duration


def run_priority_race(file_paths, background_threads, event_queue=None):
    """
    Splits file_paths into two groups (alternating assignment, so
    both groups get a similar mix of large/small files - avoiding a
    NEW confound where one group just happens to get easier files),
    then races them AGAINST EACH OTHER at two different priorities,
    at the exact same time, under the same real CPU contention.
    """
    # Alternating split: group A gets even indices, group B gets odd -
    # this keeps both groups' file-size distributions comparable,
    # rather than e.g. splitting the sorted list in half.
    group_default = file_paths[0::2]
    group_lowered = file_paths[1::2]

    stop_event = threading.Event()
    load_threads = [threading.Thread(target=_cpu_heavy_background_load, args=(stop_event,))
                     for _ in range(background_threads)]
    for t in load_threads:
        t.start()

    results = []
    results_lock = threading.Lock()

    default_result = {}
    lowered_result = {}

    def run_default():
        default_result["duration"] = _priority_runner(
            group_default, 0, "default", results, results_lock, event_queue
        )

    def run_lowered():
        lowered_result["duration"] = _priority_runner(
            group_lowered, 15, "lowered", results, results_lock, event_queue
        )

    try:
        # THE KEY FIX: both runner threads start at essentially the
        # same moment and run CONCURRENTLY, so both experience
        # identical system state (cache warmth, CPU frequency,
        # background load) throughout - priority is now the ONLY
        # variable that differs between them.
        default_thread = threading.Thread(target=run_default)
        lowered_thread = threading.Thread(target=run_lowered)

        default_thread.start()
        lowered_thread.start()

        default_thread.join()
        lowered_thread.join()
    finally:
        stop_event.set()
        for t in load_threads:
            t.join()

    default_duration = default_result["duration"]
    lowered_duration = lowered_result["duration"]

    # Throughput (files/sec) is the fairer comparison here, since the
    # two groups may have gotten a very slightly different number of
    # files depending on file_paths' length - normalizing by count
    # avoids that becoming a hidden confound of its own.
    default_throughput = len(group_default) / default_duration if default_duration > 0 else 0
    lowered_throughput = len(group_lowered) / lowered_duration if lowered_duration > 0 else 0

    if event_queue:
        event_queue.put({
            "type": "priority_race_done",
            "default_duration": default_duration, "default_count": len(group_default),
            "default_throughput": default_throughput,
            "lowered_duration": lowered_duration, "lowered_count": len(group_lowered),
            "lowered_throughput": lowered_throughput
        })

    return default_duration, lowered_duration, default_throughput, lowered_throughput