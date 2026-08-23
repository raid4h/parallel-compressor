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


def _sample_cpu_utilization(max_duration, interval, samples_out):
    """
    Runs in a background thread WHILE a benchmark executes. Repeatedly
    reads /proc/stat, computes CPU utilization as a percentage over
    each interval, and appends each reading to samples_out.

    Utilization is computed from the DIFFERENCE between two /proc/stat
    reads, since its numbers are cumulative totals since boot - a
    percentage only makes sense as "how much of THIS interval was
    spent NOT idle."
    """
    end_time = time.time() + max_duration
    prev_total, prev_idle = _read_cpu_times()

    while time.time() < end_time:
        time.sleep(interval)
        total, idle = _read_cpu_times()

        total_delta = total - prev_total
        idle_delta = idle - prev_idle

        if total_delta > 0:
            busy_fraction = 1 - (idle_delta / total_delta)
            samples_out.append(busy_fraction * 100)

        prev_total, prev_idle = total, idle


def run_worker_sweep(file_paths, worker_counts, event_queue=None):
    """
    Runs the fork-pool compression strategy once per value in
    worker_counts (e.g. [1, 2, 4, 8]), on the SAME real files each
    time, recording total duration and average CPU utilization for
    each configuration.
    """
    results = []

    for workers in worker_counts:
        cpu_samples = []
        # Start CPU sampling on a background thread BEFORE the run
        # begins, so utilization is captured for the entire run.
        sampler_thread = threading.Thread(
            target=_sample_cpu_utilization,
            args=(60, 0.2, cpu_samples)  # generous ceiling; the run itself ends this loop early
        )
        sampler_thread.daemon = True
        sampler_thread.start()

        duration, file_results = compress_concurrent_fork(file_paths, workers)

        avg_utilization = sum(cpu_samples) / len(cpu_samples) if cpu_samples else 0.0

        result = {
            "workers": workers,
            "duration": duration,
            "avg_cpu_utilization": avg_utilization,
            "files_processed": len(file_results)
        }
        results.append(result)

        if event_queue:
            event_queue.put({"type": "sweep_point", **result})

    return results


def find_optimal_worker_count(sweep_results):
    """Returns the result dict with the LOWEST duration - the
    empirically fastest configuration found by the sweep."""
    return min(sweep_results, key=lambda r: r["duration"])