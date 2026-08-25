# Parallel File Compressor

A Linux systems programming project demonstrating real process creation,
CPU scheduling, and measured performance optimization — built entirely
on genuine OS system calls (`fork()`, `exec()`, `wait()`), not simulation.

## What this is

This project compresses real files using real, separate OS processes,
created the same way a Unix shell creates them: `fork()` duplicates the
current process, and `exec()` replaces the child's memory image with
the real `gzip` program. Every experiment in this project measures
actual, reproducible performance on real data — not textbook examples
or simulated workloads.

## What it demonstrates

| Section | What it shows |
|---|---|
| 1. Worker-Count Sweep | Finds the empirically fastest number of concurrent processes for this machine, backed by 3 repeated trials (median reported) |
| 2. Bounded Pipeline | A real producer-consumer pattern: one thread discovers files while bounded worker threads compress them, with genuine backpressure |
| 3. pthreads Verification | Reads `/proc/self/task/` — a real Linux kernel interface — to prove Python's threads are genuine OS-level POSIX threads |
| 4. Task Decomposition | Compares static vs. dynamic work assignment, demonstrating the classic FCFS "convoy effect" with real numbers |
| 5. Pool Comparison | Hand-built `fork()` pool vs. Python's standard `concurrent.futures` pools — same work, different abstraction levels |
| 6. CPU Scheduling Priority Race | Two process groups at different `nice` priorities compete concurrently for real CPU time (Multilevel Queue-style) |
| 7. Scheduling Criteria | The five official metrics from CPU Scheduling coursework — CPU utilization, throughput, turnaround/waiting/response time — computed from real per-job telemetry |
| 8. Block-Level Parallel Compression | Splits one large file into chunks and compresses them simultaneously — the same technique used by `pigz`, ZFS, and Btrfs, with a verified byte-for-byte round trip |

## Why fork()/exec(), and why Linux

This project intentionally avoids Python's higher-level `multiprocessing`
abstraction in favor of raw `os.fork()` / `os.execvp()` / `os.waitpid()`
— the actual system calls taught in the course, used the same way a
real Unix shell uses them. `os.fork()` does not exist on Windows, so
this project requires a genuine Linux environment (WSL2 on Windows, or
native Linux/macOS).

## Real-world relevance

- **Section 6/7 (priority scheduling)** mirrors Multilevel Queue
  Scheduling: a real "foreground" (default priority) and "background"
  (lowered priority) group competing for CPU, arbitrated by the actual
  Linux scheduler.
- **Section 8 (block compression)** is the same technique used by the
  real tool `pigz` (parallel gzip) and by filesystems like ZFS and
  Btrfs for their multithreaded compression.
- **Section 5** shows that Python's standard `subprocess` module is
  itself just a convenience wrapper over the same `fork()`+`exec()`
  system calls this project uses directly.

## Tech stack

Pure Python 3 standard library only — `os`, `threading`, `queue`,
`tkinter`, `subprocess`, `concurrent.futures`, `mmap`, `json`,
`statistics`. No pip installs required. Uses the real `gzip` binary as
an external program.

## Project structure
parallel-compressor/ \
├── main.py entry point (GUI by default, --cli for headless) \
├── gui.py results dashboard \
├── setup_testdata.py one-command reproducible dataset setup \ 
├── compressor.py core fork()+exec()+wait() primitive \
├── benchmark.py worker-count sweep + /proc/stat CPU sampling \
├── pipeline.py bounded producer-consumer pipeline \
├── thread_proof.py pthreads verification via /proc/self/task/ \
├── decomposition.py static vs dynamic task decomposition \
├── executor_compare.py standard library pool comparison \
├── priority.py CPU scheduling priority race \
├── scheduling_metrics.py formal Scheduling Criteria computation \
├── block_compressor.py intra-file block-level parallel compression \
├── report_generator.py orchestrates all 8 sections into one report \
├── test_*.py standalone verification scripts for each module \


## How to run

Requires a real Linux environment — on Windows, use WSL2:
sudo apt update && sudo apt install -y python3 python3-tk gzip \
git clone <https://github.com/raid4h/parallel-compressor> \
cd parallel-compressor \
python3 main.py \


In the GUI, click **"Download Sample Dataset"** once — this downloads
3 real public-domain books from Project Gutenberg and builds the same
63-file test corpus every result in this project was measured against.
Then click **"Run Full Optimization Report"**.

**Note:** measured timings vary slightly between runs — this is
expected, since these are real OS-level measurements (CPU scheduling,
process creation overhead, disk I/O), not scripted output.

Alternative headless run: `python3 main.py --cli`

## Course alignment

Built to directly address feedback that a synchronization-problem
simulation project would not be accepted: this project instead uses
real system calls, real measured optimization, and real data
throughout, while still incorporating meaningful synchronization
(bounded queues, semaphores) where it's genuinely needed for the task,
not as a standalone demo.
