"""
Runs the instrumented pool at a couple of worker counts and prints a
report using the EXACT 5 official Scheduling Criteria names,
computed from real fork()+exec() job telemetry.
"""

import os
from compressor import list_files
from scheduling_metrics import run_instrumented_pool, compute_scheduling_criteria

TEST_FOLDER = os.path.expanduser("~/parallel-compressor/testdata")

if __name__ == "__main__":
    files = list_files(TEST_FOLDER)
    cpu_cores = os.cpu_count()

    for workers in [1, 4, cpu_cores]:
        print(f"\n=== Scheduling Criteria Report: {workers} worker(s) ===")

        job_records, batch_start, batch_end, cpu_samples = run_instrumented_pool(files, workers)
        criteria = compute_scheduling_criteria(job_records, batch_start, batch_end, cpu_samples)

        print(f"Jobs completed:        {criteria['num_jobs']}")
        print(f"CPU utilization:       {criteria['cpu_utilization_pct']:.1f}%")
        print(f"Throughput:            {criteria['throughput_jobs_per_sec']:.2f} jobs/sec")
        print(f"Avg turnaround time:   {criteria['avg_turnaround_time']*1000:.1f} ms")
        print(f"Avg waiting time:      {criteria['avg_waiting_time']*1000:.1f} ms")
        print(f"Avg response time:     {criteria['avg_response_time']*1000:.1f} ms")
        print(f"  (waiting time == response time here, as expected for "
              f"non-preemptive batch scheduling - each job runs to "
              f"completion once started, with no interruption to resume later)")