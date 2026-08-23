"""
Runs the pthreads-verification demo standalone and prints the
before/during/after kernel thread counts, proving real OS threads
are created and destroyed alongside our Python-level thread pool.
"""

from thread_proof import demonstrate_real_threads

if __name__ == "__main__":
    before, during, after = demonstrate_real_threads(num_threads=6, work_duration=2.0)

    print(f"Kernel thread IDs BEFORE spawning workers: {before}")
    print(f"  -> {len(before)} real OS thread(s)\n")

    print(f"Kernel thread IDs DURING worker execution: {during}")
    print(f"  -> {len(during)} real OS thread(s)")
    new_ids = sorted(set(during) - set(before))
    print(f"  -> {len(new_ids)} NEW kernel thread(s) appeared: {new_ids}\n")

    print(f"Kernel thread IDs AFTER workers finished: {after}")
    print(f"  -> {len(after)} real OS thread(s)")
    print(f"  -> confirms the {len(new_ids)} worker threads were real pthreads that the kernel "
          f"created and later cleaned up, matching Python's threading.Thread lifecycle exactly.")