"""
Computes the 5 official 'Scheduling Criteria' from CPU
utilization, throughput, turnaround time, waiting time, response
time, measured from REAL telemetry of our actual fork()+exec() jobs
- not from a textbook Gantt chart of hypothetical processes.

Definitions used (matching lecture exactly):
  - Arrival time:    when a job becomes ready to run (submitted to
                      the worker pool)
  - Start time:      when the job actually begins running (worker
                      slot acquired, fork()+exec() begins)
  - Completion time: when the job finishes (wait() returns)
  - Burst time:      completion_time - start_time (the real 'CPU
                      burst' - actual service time once running)
  - Turnaround time: completion_time - arrival_time
  - Waiting time:    turnaround_time - burst_time (time spent
                      queued, NOT running)
  - Response time:   start_time - arrival_time (time until the job
                      first begins producing results)

NOTE (a real, correct observation, not a simplification): because
every job here runs to completion once started - no preemption
WITHIN a job - waiting time and response time are numerically
IDENTICAL in this model, both equal to start_time - arrival_time.
This differs from preemptive schemes (Round Robin, SRTF) where a job
can be paused and resumed multiple times, making the two diverge.
This is itself a legitimate, quotable insight about non-preemptive
batch scheduling, not a limitation to hide.
"""

import time
import threading

from compressor import compress_one_file
from benchmark import _read_cpu_times  # reuse the /proc/stat reader already built


def run_instrumented_pool(file_paths, max_workers, event_queue=None):
    """
    Runs the same semaphore-bounded fork pool as compress_concurrent_fork(),
    but additionally records arrival/start/completion timestamps for
    EVERY job, so the 5 official scheduling criteria can be computed
    afterward from real, per-job data.
    """
    semaphore = threading.Semaphore(max_workers)
    job_records = []
    records_lock = threading.Lock()

    batch_start = time.time()
    # Sample real kernel CPU counters at the very start and end of the
    # whole batch, the same /proc/stat technique used in benchmark.py.
    cpu_start_total, cpu_start_idle = _read_cpu_times()

    def worker(path, arrival_time):
        semaphore.acquire()  # BLOCKS here if the pool is full - this IS the "waiting" period
        start_time = time.time()  # the job genuinely begins running NOW

        success, _ = compress_one_file(path)

        completion_time = time.time()
        semaphore.release()

        record = {
            "path": path,
            "arrival": arrival_time,
            "start": start_time,
            "completion": completion_time,
            "success": success,
        }
        with records_lock:
            job_records.append(record)

        if event_queue:
            event_queue.put({"type": "metrics_job_done", **record})

    threads = []
    for path in file_paths:
        # A job "arrives" (becomes ready to run) the moment it's
        # submitted to the pool - captured BEFORE the thread that will
        # eventually run it is even created, matching the lecture
        # definition of arrival time exactly.
        arrival_time = time.time()
        t = threading.Thread(target=worker, args=(path, arrival_time))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    batch_end = time.time()
    cpu_end_total, cpu_end_idle = _read_cpu_times()

    cpu_samples = (cpu_start_total, cpu_start_idle, cpu_end_total, cpu_end_idle)
    return job_records, batch_start, batch_end, cpu_samples


def compute_scheduling_criteria(job_records, batch_start, batch_end, cpu_samples):
    """
    Computes all 5 official Scheduling Criteria from the raw job
    records.
    """
    n = len(job_records)
    if n == 0:
        return None

    turnaround_times, waiting_times, response_times, burst_times = [], [], [], []

    for record in job_records:
        arrival = record["arrival"]
        start = record["start"]
        completion = record["completion"]

        burst = completion - start
        turnaround = completion - arrival
        waiting = turnaround - burst          # time spent queued, not running
        response = start - arrival             # explicit, matches lecture's own definition directly

        burst_times.append(burst)
        turnaround_times.append(turnaround)
        waiting_times.append(waiting)
        response_times.append(response)

    total_batch_time = batch_end - batch_start
    throughput = n / total_batch_time if total_batch_time > 0 else 0

    cpu_start_total, cpu_start_idle, cpu_end_total, cpu_end_idle = cpu_samples
    total_delta = cpu_end_total - cpu_start_total
    idle_delta = cpu_end_idle - cpu_start_idle
    cpu_utilization = (1 - (idle_delta / total_delta)) * 100 if total_delta > 0 else 0

    return {
        "num_jobs": n,
        "cpu_utilization_pct": cpu_utilization,
        "throughput_jobs_per_sec": throughput,
        "avg_turnaround_time": sum(turnaround_times) / n,
        "avg_waiting_time": sum(waiting_times) / n,
        "avg_response_time": sum(response_times) / n,
        "avg_burst_time": sum(burst_times) / n,
    }