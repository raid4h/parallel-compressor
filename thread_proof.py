"""
PROVES that Python's threading module creates REAL POSIX threads
(pthreads) on Linux, rather than just claiming it - by reading
/proc/self/task/, a real kernel interface that lists one subdirectory
per ACTUAL OS-level thread of the currently running process. Each
subdirectory name IS that thread's real kernel thread ID (TID).

This directly answers "system call / API interface... pthreads": we
are not calling pthread_create() ourselves (CPython does that
internally when you call threading.Thread.start()), but we CAN
directly observe, from the kernel's own bookkeeping, that real OS
threads are being created and destroyed as our pool runs.
"""

import os
import time
import threading


def list_kernel_thread_ids():
    """
    Returns the current REAL kernel thread IDs (TIDs) of this process,
    read directly from /proc/self/task/ - one entry per actual OS
    thread that currently exists, as tracked by the Linux kernel
    itself, not by Python.
    """
    task_dir = "/proc/self/task"
    return sorted(int(name) for name in os.listdir(task_dir))


def demonstrate_real_threads(num_threads, work_duration, event_queue=None):
    """
    Spins up num_threads real threading.Thread objects, each doing
    some CPU work for work_duration seconds, and samples
    /proc/self/task/ before, during, and after - showing the kernel's
    own thread count and thread IDs change in lockstep with our
    Python-level thread creation/completion.
    """
    before_ids = list_kernel_thread_ids()
    if event_queue:
        event_queue.put({"type": "thread_proof_sample", "label": "before", "tids": before_ids})

    barrier = threading.Barrier(num_threads + 1)  # +1 for this main thread, to synchronize the "during" sample

    def worker(thread_index):
        # threading.get_native_id() (Python 3.8+) returns THIS
        # thread's real kernel TID directly, as an extra confirmation
        # alongside the /proc/self/task/ listing above.
        native_id = threading.get_native_id()
        if event_queue:
            event_queue.put({
                "type": "thread_proof_worker_id", "thread_index": thread_index, "native_id": native_id
            })

        barrier.wait()  # pause here until every worker (and main) has reached this point

        end_time = time.time() + work_duration
        total = 0
        while time.time() < end_time:
            total += 1  # trivial busy-work, just enough to keep the thread alive/measurable

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(num_threads)]
    for t in threads:
        t.start()

    barrier.wait()  # blocks main thread here until ALL workers have reached their own barrier.wait()

    # At this exact moment, every worker thread is confirmed alive and
    # running - the ideal point to sample /proc/self/task/ for the
    # "during" snapshot, since we're guaranteed all num_threads extra
    # kernel threads currently exist.
    during_ids = list_kernel_thread_ids()
    if event_queue:
        event_queue.put({"type": "thread_proof_sample", "label": "during", "tids": during_ids})

    for t in threads:
        t.join()

    after_ids = list_kernel_thread_ids()
    if event_queue:
        event_queue.put({"type": "thread_proof_sample", "label": "after", "tids": after_ids})

    return before_ids, during_ids, after_ids