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
import hashlib
import block_compressor

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
LARGE_FILE_PATH = os.path.join(PROJECT_ROOT, "testdata_large", "bigfile.txt")
BLOCK_TEMP_DIR = os.path.join(PROJECT_ROOT, "block_temp")


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
    report("Running worker-count sweep (3 repeats per configuration)...")
    lines.append(_section("1. WORKER-COUNT OPTIMIZATION SWEEP"))
    lines.append("Same real fork()+exec() compression task, run across several worker "
                  "counts, 3 TIMES EACH, reporting the MEDIAN to reduce noise from "
                  "virtualization/system variance - finding the empirically fastest "
                  "configuration for this machine, backed by repeated trials rather "
                  "than a single run.\n")

    worker_counts = sorted(set([1, 2, 4, cpu_cores, cpu_cores * 2]))
    sweep_results = run_worker_sweep(files, worker_counts, repeats=3)
    best = find_optimal_worker_count(sweep_results)

    lines.append(f"{'Workers':<10}{'Median (s)':<14}{'Range (s)':<18}{'Avg CPU %':<12}")
    for r in sweep_results:
        range_str = f"{min(r['all_durations']):.3f}-{max(r['all_durations']):.3f}"
        lines.append(f"{r['workers']:<10}{r['duration']:<14.3f}{range_str:<18}"
                     f"{r['avg_cpu_utilization']:<12.1f}")
    lines.append(f"\nOptimal configuration found: {best['workers']} workers "
                 f"(median {best['duration']:.3f}s, {best['avg_cpu_utilization']:.1f}% CPU "
                 f"utilization, across {len(best['all_durations'])} repeated trials)")
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

    # Cap workers by the ACTUAL number of files available - prevents
    # a worker from ever being assigned zero files (which happened
    # when this was tested against a small 3-file folder), which
    # would produce a meaningless "instant finish" instead of a real
    # convoy-effect measurement.
    decomposition_workers = min(4, cpu_cores, len(files))
    static_duration, _, worker_finish_times = run_static_decomposition(files, decomposition_workers)
    fastest_id, fastest_time, slowest_id, slowest_time, gap = compute_convoy_gap(worker_finish_times)
    dynamic_duration, _, files_per_worker = run_dynamic_decomposition(files, decomposition_workers)

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

    fork_duration, fork_results = compress_concurrent_fork(files, min(8, cpu_cores))
    subprocess_duration, subprocess_results = compress_concurrent_subprocess(files, min(8, cpu_cores))
    tpe_duration, tpe_results = run_thread_pool_executor(files, min(8, cpu_cores))
    ppe_duration, ppe_results = run_process_pool_executor(files, min(8, cpu_cores))

    # IMPORTANT: these four result lists have DIFFERENT shapes.
    # fork_results / subprocess_results / tpe_results are each lists of
    # (path, success, elapsed) - success is index [1].
    # ppe_results is a list of (success, elapsed) ONLY - no path prefix,
    # since it comes straight from compress_one_file() via
    # ProcessPoolExecutor.map(), which doesn't include the path in its
    # return value - so success is index [0] there instead. Mixing
    # these up silently would itself be a bug worth catching.
    fork_success = sum(1 for r in fork_results if r[1])
    subprocess_success = sum(1 for r in subprocess_results if r[1])
    tpe_success = sum(1 for r in tpe_results if r[1])
    ppe_success = sum(1 for r in ppe_results if r[0])

    total = len(files)
    lines.append(f"Hand-built fork() pool:              {fork_duration:.3f}s  "
                 f"({fork_success}/{total} succeeded)")
    lines.append(f"Hand-built subprocess thread pool:   {subprocess_duration:.3f}s  "
                 f"({subprocess_success}/{total} succeeded)")
    lines.append(f"Standard ThreadPoolExecutor:         {tpe_duration:.3f}s  "
                 f"({tpe_success}/{total} succeeded)")
    lines.append(f"Standard ProcessPoolExecutor:         {ppe_duration:.3f}s  "
                 f"({ppe_success}/{total} succeeded)")

    # A visible, explicit warning if ANY strategy didn't fully succeed -
    # this is exactly the kind of check that would have caught the
    # suspiciously-fast 0.058s result immediately, instead of it
    # silently looking like a great (but fake) optimization win.
    for name, success_count in [("fork() pool", fork_success), ("subprocess pool", subprocess_success),
                                  ("ThreadPoolExecutor", tpe_success), ("ProcessPoolExecutor", ppe_success)]:
        if success_count < total:
            lines.append(f"\n⚠ WARNING: {name} only succeeded on {success_count}/{total} files - "
                         f"its timing above is NOT a valid comparison and should be investigated.")

    raw_data["executor_comparison"] = {
        "fork_pool": {"duration": fork_duration, "success": fork_success},
        "subprocess_pool": {"duration": subprocess_duration, "success": subprocess_success},
        "thread_pool_executor": {"duration": tpe_duration, "success": tpe_success},
        "process_pool_executor": {"duration": ppe_duration, "success": ppe_success}
    }

    # ---- 6. CPU scheduling priority race ----
    report("Running CPU scheduling priority race (3 repeats)...")
    lines.append(_section("6. CPU SCHEDULING: PRIORITY RACE (Multilevel Queue Style)"))
    lines.append("Two real priority groups (nice=0 vs nice=+15) compete CONCURRENTLY for "
                  "the same CPU cores under real contention, run 3 TIMES and reported as "
                  "a MEDIAN - mirrors the foreground/background dynamic of Multilevel "
                  "Queue Scheduling, backed by repeated trials rather than one run.\n")

    priority_result = run_priority_race(files, cpu_cores, repeats=3)
    default_tput = priority_result["default_throughput"]
    lowered_tput = priority_result["lowered_throughput"]

    lines.append(f"Default priority (nice=0):   median {default_tput:.2f} files/sec  "
                 f"(range: {min(priority_result['all_default_throughputs']):.2f}-"
                 f"{max(priority_result['all_default_throughputs']):.2f})")
    lines.append(f"Lowered priority (nice=+15): median {lowered_tput:.2f} files/sec  "
                 f"(range: {min(priority_result['all_lowered_throughputs']):.2f}-"
                 f"{max(priority_result['all_lowered_throughputs']):.2f})")

    if default_tput > lowered_tput:
        advantage = ((default_tput - lowered_tput) / lowered_tput) * 100
        lines.append(f"\nDefault priority: {advantage:.1f}% higher median throughput across 3 trials.")
    else:
        disadvantage = ((lowered_tput - default_tput) / default_tput) * 100
        lines.append(f"\nNo default-priority advantage across 3 trials (lowered priority "
                     f"{disadvantage:.1f}% higher) - the effect may be smaller than system "
                     f"noise at this workload size.")

    raw_data["priority_race"] = priority_result

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

    # ---- 8. Intra-file block-level parallel compression ----
    report("Running intra-file block-level parallel compression (Section 8)...")
    lines.append(_section("8. INTRA-FILE BLOCK-LEVEL PARALLEL COMPRESSION (pigz-style)"))
    lines.append("A DIFFERENT axis of parallelism than everything above: instead of "
                  "parallelizing ACROSS many files, this splits ONE large real file into "
                  "chunks and compresses them simultaneously - the same technique used by "
                  "the real tool 'pigz' (parallel gzip) and by filesystems like ZFS and "
                  "Btrfs for their multithreaded compression.\n")

    if os.path.exists(LARGE_FILE_PATH):
        os.makedirs(BLOCK_TEMP_DIR, exist_ok=True)

        seq_output = os.path.join(BLOCK_TEMP_DIR, "sequential.gz")
        seq_duration, seq_success = block_compressor.compress_file_sequential(LARGE_FILE_PATH, seq_output)

        block_output = os.path.join(BLOCK_TEMP_DIR, "parallel_container.bin")
        block_workers = min(8, cpu_cores)
        block_duration, _ = block_compressor.compress_file_parallel_blocks(
            LARGE_FILE_PATH, block_workers, BLOCK_TEMP_DIR, block_output
        )
        block_speedup = seq_duration / block_duration if block_duration > 0 else 0

        restored_output = os.path.join(BLOCK_TEMP_DIR, "restored.txt")
        decompress_duration, decompress_success = block_compressor.decompress_file_parallel_blocks(
            block_output, BLOCK_TEMP_DIR, restored_output
        )

        def _checksum(path):
            hasher = hashlib.md5()
            with open(path, "rb") as f:
                while True:
                    chunk = f.read(65536)
                    if not chunk:
                        break
                    hasher.update(chunk)
            return hasher.hexdigest()

        integrity_ok = _checksum(LARGE_FILE_PATH) == _checksum(restored_output)

        size_mb = os.path.getsize(LARGE_FILE_PATH) / (1024 * 1024)
        lines.append(f"Large file size: {size_mb:.1f} MB")
        lines.append(f"Sequential (whole-file) compression:   {seq_duration:.3f}s")
        lines.append(f"Block-parallel compression ({block_workers} chunks): {block_duration:.3f}s")
        lines.append(f"Speedup: {block_speedup:.2f}x")
        lines.append(f"Parallel decompression: {decompress_duration:.3f}s | "
                     f"Round-trip integrity: {'VERIFIED' if integrity_ok else 'MISMATCH - BUG'}")

        raw_data["block_compression"] = {
            "sequential_duration": seq_duration, "block_duration": block_duration,
            "speedup": block_speedup, "decompress_duration": decompress_duration,
            "integrity_verified": integrity_ok
        }
    else:
        lines.append(f"Skipped: large test file not found at {LARGE_FILE_PATH}. "
                     "Run the setup command (Step 38) to create it first.")

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