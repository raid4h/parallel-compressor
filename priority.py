"""
CPU SCHEDULING experiment, redesigned as a genuine CONCURRENT race
rather than two sequential batches (the original sequential design
was vulnerable to page-cache and CPU-frequency-ramp-up confounds
between the two runs, which produced a misleading result).

This mirrors MULTILEVEL QUEUE SCHEDULING: a 'foreground' group
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
import statistics

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

def run_priority_race(file_paths, background_threads, event_queue=None, repeats=3):
    """
    Runs the concurrent priority race REPEATS times (same file split
    each time, so we're only averaging out SYSTEM noise between
    trials, not introducing new variables), and reports the MEDIAN
    throughput for each priority group - a single race can be noisy
    inside a virtualized environment like WSL2, so one run isn't
    reliable evidence either way (as your own results showed: +5.8%,
    +21.3%, then -0.9% across three separate single-trial runs).
    """
    group_default = file_paths[0::2]
    group_lowered = file_paths[1::2]

    default_durations = []
    lowered_durations = []
    default_throughputs = []
    lowered_throughputs = []

    for repeat_index in range(repeats):
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

        d_dur = default_result["duration"]
        l_dur = lowered_result["duration"]
        d_tput = len(group_default) / d_dur if d_dur > 0 else 0
        l_tput = len(group_lowered) / l_dur if l_dur > 0 else 0

        default_durations.append(d_dur)
        lowered_durations.append(l_dur)
        default_throughputs.append(d_tput)
        lowered_throughputs.append(l_tput)

        if event_queue:
            event_queue.put({
                "type": "priority_race_repeat_done", "repeat": repeat_index + 1, "repeats": repeats,
                "default_throughput": d_tput, "lowered_throughput": l_tput
            })

    result = {
        "default_duration": statistics.median(default_durations),
        "lowered_duration": statistics.median(lowered_durations),
        "default_throughput": statistics.median(default_throughputs),
        "lowered_throughput": statistics.median(lowered_throughputs),
        "all_default_throughputs": default_throughputs,      # raw repeats kept for transparency
        "all_lowered_throughputs": lowered_throughputs,
        "default_count": len(group_default),
        "lowered_count": len(group_lowered),
    }

    if event_queue:
        event_queue.put({"type": "priority_race_done", **result})

    return result