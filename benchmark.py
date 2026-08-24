"""
Optimization layer: runs the fork-pool compression strategy across a
RANGE of different worker counts on the SAME real files, to find the
empirically fastest setting for this specific machine - the actual
'optimization' deliverable, not just a single demo run.

Also samples real system-wide CPU utilization directly from the Linux
kernel's /proc/stat interface while each run executes, so we can see
NOT just how long each configuration took, but how effectively it
used the machine's actual CPU cores - real system-level data, read
directly from the kernel's exposed statistics, not a library wrapper.
"""

import os
import time
import threading
import statistics  

from compressor import compress_concurrent_fork


def _read_cpu_times():
    """
    Reads the first line of /proc/stat, which the Linux kernel updates
    continuously with cumulative CPU time spent in each mode (user,
    system, idle, etc.) since boot, summed across ALL cores. This is
    a direct read of a kernel-exposed interface - the raw data source
    that monitoring libraries themselves read from underneath.

    Returns (total_time, idle_time), both in raw kernel "jiffies".
    """
    with open("/proc/stat", "r") as f:
        first_line = f.readline()

    # Example line: "cpu  132453 320 45678 9081726 ..."
    # Fields after 'cpu' are: user, nice, system, idle, iowait, irq,
    # softirq, steal, guest, guest_nice.
    parts = first_line.split()
    values = [int(x) for x in parts[1:]]

    idle_time = values[3]  # 4th field is 'idle'
    total_time = sum(values)
    return total_time, idle_time


def _sample_cpu_utilization(max_duration, interval, samples_out, stop_event):
    """
    Runs in a background thread WHILE a benchmark executes. Repeatedly
    reads /proc/stat and computes CPU utilization as a percentage.

    stop_event lets the CALLER signal "the real work is done, stop
    sampling now" - without this, the loop only exits after
    max_duration regardless of how quickly the actual work finished,
    leaving stray background threads alive long after they're needed
    (exactly the bug that produced "6 threads" instead of "1" in the
    pthreads verification step later in the report).
    """
    end_time = time.time() + max_duration
    prev_total, prev_idle = _read_cpu_times()

    while time.time() < end_time and not stop_event.is_set():
        time.sleep(interval)
        total, idle = _read_cpu_times()

        total_delta = total - prev_total
        idle_delta = idle - prev_idle

        if total_delta > 0:
            busy_fraction = 1 - (idle_delta / total_delta)
            samples_out.append(busy_fraction * 100)

        prev_total, prev_idle = total, idle

def run_worker_sweep(file_paths, worker_counts, event_queue=None, repeats=3):
    """
    Runs the fork-pool compression strategy REPEATS times per value in
    worker_counts, and reports the MEDIAN duration/utilization across
    those repeats - a single run's numbers can be noisy, especially
    inside a virtualized environment like WSL2 that shares real CPU
    and scheduling resources with the host Windows OS.

    Median (rather than mean) is used deliberately: it's robust to
    occasional outlier runs (e.g. one run that happens to overlap with
    an unrelated background OS/host process spike) without a single
    bad run skewing the reported "typical" performance the way an
    average would.
    """
    results = []

    for workers in worker_counts:
        run_durations = []
        run_utilizations = []
        file_count = 0

        for repeat_index in range(repeats):
            cpu_samples = []
            stop_event = threading.Event()

            sampler_thread = threading.Thread(
                target=_sample_cpu_utilization,
                args=(60, 0.2, cpu_samples, stop_event)
            )
            sampler_thread.daemon = True
            sampler_thread.start()

            duration, file_results = compress_concurrent_fork(file_paths, workers)

            stop_event.set()
            sampler_thread.join(timeout=1)

            avg_utilization = sum(cpu_samples) / len(cpu_samples) if cpu_samples else 0.0

            run_durations.append(duration)
            run_utilizations.append(avg_utilization)
            file_count = len(file_results)  # same every repeat, just kept from the last one

            if event_queue:
                event_queue.put({
                    "type": "sweep_repeat_done", "workers": workers,
                    "repeat": repeat_index + 1, "repeats": repeats,
                    "duration": duration, "cpu_utilization": avg_utilization
                })

        median_duration = statistics.median(run_durations)
        median_utilization = statistics.median(run_utilizations)

        result = {
            "workers": workers,
            "duration": median_duration,               # the MEDIAN, used everywhere downstream
            "avg_cpu_utilization": median_utilization,
            "all_durations": run_durations,             # raw repeats kept for transparency/appendix
            "all_utilizations": run_utilizations,
            "files_processed": file_count
        }
        results.append(result)

        if event_queue:
            event_queue.put({"type": "sweep_point", **result})

    return results


def find_optimal_worker_count(sweep_results):
    """Returns the result dict with the LOWEST duration - the
    empirically fastest configuration found by the sweep."""
    return min(sweep_results, key=lambda r: r["duration"])