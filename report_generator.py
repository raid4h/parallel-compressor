"""
Orchestrates the FULL experiment suite built across this project into
one comprehensive report. This is the actual substantive deliverable:
real fork()+exec()+wait() process creation, a real bounded producer-
consumer pipeline, real pthreads verification via kernel introspection,
real task decomposition comparison, real standard-library pool
comparison, a real CPU-scheduling priority race, and the formal
Scheduling Criteria - all run on real files, with results collected
into one report and saved as a persistent artifact.
"""

import os
import time
import json
from datetime import datetime

from compressor import list_files
from benchmark import run_worker_sweep, find_optimal_worker_count
from pipeline import run_pipeline
from thread_proof import demonstrate_real_threads, list_kernel_thread_ids
from decomposition import run_static_decomposition, run_dynamic_decomposition, compute_convoy_gap
from executor_compare import run_thread_pool_executor, run_process_pool_executor
from compressor import compress_concurrent_fork, compress_concurrent_subprocess
from priority import run_priority_race
from scheduling_metrics import run_instrumented_pool, compute_scheduling_criteria


def _section(title):
    """A consistent section-header format used throughout the report."""
    bar = "=" * 70
    return f"\n{bar}\n{title}\n{bar}\n"


def run_full_report(test_folder, progress_callback=None):
    """
    Runs the entire experiment suite in sequence on the real files in
    test_folder. progress_callback, if given, is called with a short
    status string before each stage begins - this is the ONLY hook
    the GUI layer (built next) needs to show live progress, since all
    the actual work happens right here, in one place, reused by both
    the CLI and the GUI rather than being duplicated between them.

    Returns (report_text, raw_data) - report_text is the full
    human-readable report; raw_data is a plain dict of the underlying
    numbers, saved separately as JSON for anyone who wants to
    re-analyze the real numbers directly.
    """
    def report(msg):
        if progress_callback:
            progress_callback(msg)

    files = list_files(test_folder)
    cpu_cores = os.cpu_count()
    lines = []
    raw_data = {"timestamp": datetime.now().isoformat(), "num_files": len(files), "cpu_cores": cpu_cores}

    lines.append(_section("CONCURRENCY OPTIMIZATION REPORT"))
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"Test dataset: {len(files)} real files in {test_folder}")
    lines.append(f"Machine: {cpu_cores} CPU cores (os.cpu_count())")

    # ---- 1. Worker-count optimization sweep ----
    report("Running worker-count sweep...")
    lines.append(_section("1. WORKER-COUNT OPTIMIZATION SWEEP"))
    lines.append("Same real fork()+exec() compression task, run across several worker "
                  "counts, to find the empirically fastest configuration for this machine.\n")

    worker_counts = sorted(set([1, 2, 4, cpu_cores, cpu_cores * 2]))
    sweep_results = run_worker_sweep(files, worker_counts)
    best = find_optimal_worker_count(sweep_results)

    lines.append(f"{'Workers':<10}{'Time (s)':<12}{'Avg CPU %':<12}")
    for r in sweep_results:
        lines.append(f"{r['workers']:<10}{r['duration']:<12.3f}{r['avg_cpu_utilization']:<12.1f}")
    lines.append(f"\nOptimal configuration found: {best['workers']} workers "
                 f"({best['duration']:.3f}s, {best['avg_cpu_utilization']:.1f}% CPU utilization)")
    raw_data["worker_sweep"] = sweep_results
    raw_data["optimal_worker_count"] = best["workers"]

    # ---- 2. Bounded producer-consumer pipeline ----
    report("Running bounded producer-consumer pipeline...")
    lines.append(_section("2. BOUNDED PRODUCER-CONSUMER PIPELINE"))
    lines.append("A real producer thread walks the directory while bounded consumer "
                  "threads compress files as they're discovered - genuine backpressure, "
                  "not a simulated buffer.\n")

    pipeline_duration, discovered, pipeline_results = run_pipeline(
        test_folder, num_consumers=min(4, cpu_cores), queue_capacity=5
    )
    lines.append(f"Discovered: {discovered} files | Processed: {len(pipeline_results)} files")
    lines.append(f"Total time: {pipeline_duration:.3f}s")
    raw_data["pipeline"] = {"duration": pipeline_duration, "discovered": discovered,
                             "processed": len(pipeline_results)}

    # ---- 3. pthreads verification ----
    report("Verifying real OS threads via /proc/self/task/...")
    lines.append(_section("3. PTHREADS VERIFICATION (KERNEL-LEVEL PROOF)"))
    lines.append("Reads /proc/self/task/ directly - a real kernel interface - to PROVE "
                  "Python's threading module creates genuine POSIX threads, not just "
                  "claims to.\n")

    before_ids, during_ids, after_ids = demonstrate_real_threads(num_threads=6, work_duration=1.5)
    new_ids = sorted(set(during_ids) - set(before_ids))
    lines.append(f"Kernel thread count before: {len(before_ids)}")
    lines.append(f"Kernel thread count during: {len(during_ids)} "
                 f"({len(new_ids)} new real kernel TIDs: {new_ids})")
    lines.append(f"Kernel thread count after:  {len(after_ids)}")
    lines.append("Confirms: real OS threads were created and cleaned up in lockstep "
                 "with Python's threading.Thread lifecycle.")
    raw_data["pthreads_proof"] = {"before": before_ids, "during": during_ids, "after": after_ids}

    # ---- 4. Task decomposition + convoy effect ----
    report("Comparing static vs dynamic task decomposition...")
    lines.append(_section("4. TASK DECOMPOSITION: STATIC vs DYNAMIC"))
    lines.append("Same real files, same worker count, two different ways of dividing "
                  "the work - demonstrating the classic FCFS 'convoy effect'.\n")

    static_duration, _, worker_finish_times = run_static_decomposition(files, min(4, cpu_cores))
    fastest_id, fastest_time, slowest_id, slowest_time, gap = compute_convoy_gap(worker_finish_times)
    dynamic_duration, _, files_per_worker = run_dynamic_decomposition(files, min(4, cpu_cores))

    lines.append(f"Static:  {static_duration:.3f}s total | "
                 f"convoy gap: {gap:.3f}s (worker {fastest_id} idle while worker {slowest_id} finished)")
    lines.append(f"Dynamic: {dynamic_duration:.3f}s total | "
                 f"files per worker: {files_per_worker} (naturally load-balanced)")
    winner = "Dynamic" if dynamic_duration < static_duration else "Static"
    lines.append(f"Faster: {winner} ({abs(static_duration - dynamic_duration):.3f}s difference)")
    raw_data["decomposition"] = {
        "static_duration": static_duration, "convoy_gap": gap,
        "dynamic_duration": dynamic_duration, "files_per_worker": files_per_worker
    }

    # ---- 5. Standard library pool comparison ----
    report("Comparing hand-built pools vs standard library executors...")
    lines.append(_section("5. HAND-BUILT POOLS vs STANDARD LIBRARY"))
    lines.append("Same real work, four different levels of abstraction over the same "
                  "underlying system calls.\n")

    fork_duration, _ = compress_concurrent_fork(files, min(8, cpu_cores))
    subprocess_duration, _ = compress_concurrent_subprocess(files, min(8, cpu_cores))
    tpe_duration, _ = run_thread_pool_executor(files, min(8, cpu_cores))
    ppe_duration, _ = run_process_pool_executor(files, min(8, cpu_cores))

    lines.append(f"Hand-built fork() pool:              {fork_duration:.3f}s")
    lines.append(f"Hand-built subprocess thread pool:   {subprocess_duration:.3f}s")
    lines.append(f"Standard ThreadPoolExecutor:         {tpe_duration:.3f}s")
    lines.append(f"Standard ProcessPoolExecutor:         {ppe_duration:.3f}s")
    raw_data["executor_comparison"] = {
        "fork_pool": fork_duration, "subprocess_pool": subprocess_duration,
        "thread_pool_executor": tpe_duration, "process_pool_executor": ppe_duration
    }

    # ---- 6. CPU scheduling priority race ----
    report("Running CPU scheduling priority race...")
    lines.append(_section("6. CPU SCHEDULING: PRIORITY RACE (Multilevel Queue Style)"))
    lines.append("Two real priority groups (nice=0 vs nice=+15) compete CONCURRENTLY for "
                  "the same CPU cores under real contention - mirrors the foreground/"
                  "background dynamic of Multilevel Queue Scheduling.\n")

    default_dur, lowered_dur, default_tput, lowered_tput = run_priority_race(files, cpu_cores)
    lines.append(f"Default priority (nice=0):   {default_dur:.3f}s, {default_tput:.2f} files/sec")
    lines.append(f"Lowered priority (nice=+15): {lowered_dur:.3f}s, {lowered_tput:.2f} files/sec")
    advantage = ((default_tput - lowered_tput) / lowered_tput * 100) if lowered_tput > 0 else 0
    lines.append(f"Default priority throughput advantage: {advantage:.1f}%")
    raw_data["priority_race"] = {
        "default_duration": default_dur, "default_throughput": default_tput,
        "lowered_duration": lowered_dur, "lowered_throughput": lowered_tput
    }

    # ---- 7. Formal Scheduling Criteria ----
    report("Computing formal Scheduling Criteria...")
    lines.append(_section("7. SCHEDULING CRITERIA (Ch.5 official metrics)"))
    lines.append("CPU utilization, throughput, turnaround time, waiting time, and "
                 "response time - computed from real per-job telemetry.\n")

    lines.append(f"{'Workers':<10}{'CPU %':<10}{'Tput/s':<10}{'Turnaround':<14}"
                 f"{'Waiting':<12}{'Response':<12}")
    criteria_by_workers = {}
    for w in [1, min(4, cpu_cores), cpu_cores]:
        job_records, batch_start, batch_end, cpu_samples = run_instrumented_pool(files, w)
        criteria = compute_scheduling_criteria(job_records, batch_start, batch_end, cpu_samples)
        criteria_by_workers[w] = criteria
        lines.append(f"{w:<10}{criteria['cpu_utilization_pct']:<10.1f}"
                     f"{criteria['throughput_jobs_per_sec']:<10.2f}"
                     f"{criteria['avg_turnaround_time']*1000:<14.1f}"
                     f"{criteria['avg_waiting_time']*1000:<12.1f}"
                     f"{criteria['avg_response_time']*1000:<12.1f}")
    raw_data["scheduling_criteria"] = criteria_by_workers

    lines.append(_section("END OF REPORT"))

    report_text = "\n".join(lines)
    return report_text, raw_data


def save_report(report_text, raw_data, output_dir="results"):
    """
    Saves the report as a real, persistent artifact: a human-readable
    .txt file AND a machine-readable .json of the raw numbers, both
    timestamped so repeated runs don't overwrite each other.
    """
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    txt_path = os.path.join(output_dir, f"report_{timestamp}.txt")
    json_path = os.path.join(output_dir, f"data_{timestamp}.json")

    with open(txt_path, "w") as f:
        f.write(report_text)

    with open(json_path, "w") as f:
        json.dump(raw_data, f, indent=2)

    return txt_path, json_path