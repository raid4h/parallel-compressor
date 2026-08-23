"""
Compares two TASK DECOMPOSITION strategies for distributing real files
across a fixed pool of worker threads, each launching real fork()+exec()
child processes:

  STATIC partitioning: split the file list into N roughly-equal chunks
  UP FRONT (one chunk per worker), before any work begins. Simple, but
  can leave some workers idle early while others are still stuck on a
  chunk containing larger files.

  DYNAMIC partitioning: a single shared queue.Queue holds ALL files;
  each worker repeatedly pulls the NEXT available file the moment it
  finishes its current one. Naturally load-balances: a worker that
  gets lucky with small files simply pulls more files overall.

Our real test dataset (3 different books, duplicated) has genuinely
UNEVEN file content lengths in terms of compression time, making this
comparison meaningful rather than purely theoretical.
"""

import threading
import queue
import time

from compressor import compress_one_file


def run_static_decomposition(file_paths, num_workers, event_queue=None):
    """
    Splits file_paths into num_workers chunks UP FRONT using slice
    striping (file 0 to worker 0, file 1 to worker 1, ... wrapping
    around), then each worker processes its OWN fixed chunk with no
    further coordination needed once started.
    """
    start = time.time()

    # Slice striping: worker i gets every num_workers-th file,
    # starting at index i - a simple, deterministic static split.
    chunks = [file_paths[i::num_workers] for i in range(num_workers)]

    results = []
    results_lock = threading.Lock()

    def worker(chunk, worker_id):
        for path in chunk:
            success, elapsed = compress_one_file(path)
            with results_lock:
                results.append((path, success, elapsed))
            if event_queue:
                event_queue.put({
                    "type": "decomposition_file_done", "strategy": "static",
                    "worker_id": worker_id, "path": path, "elapsed": elapsed
                })

    threads = [threading.Thread(target=worker, args=(chunks[i], i)) for i in range(num_workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    duration = time.time() - start
    return duration, results


def run_dynamic_decomposition(file_paths, num_workers, event_queue=None):
    """
    Puts every file into ONE shared queue.Queue up front. Each worker
    repeatedly pulls the next available file as soon as it's free -
    no worker is ever assigned a fixed chunk, so faster workers (or
    workers that happen to get smaller files) naturally end up
    processing MORE files overall than slower ones.
    """
    start = time.time()

    work_queue = queue.Queue()
    for path in file_paths:
        work_queue.put(path)

    results = []
    results_lock = threading.Lock()
    files_per_worker = {}  # tracks how many files EACH worker actually ended up handling
    files_per_worker_lock = threading.Lock()

    def worker(worker_id):
        count = 0
        while True:
            try:
                path = work_queue.get_nowait()
            except queue.Empty:
                break  # no files left anywhere - this worker is done

            success, elapsed = compress_one_file(path)
            count += 1
            with results_lock:
                results.append((path, success, elapsed))
            if event_queue:
                event_queue.put({
                    "type": "decomposition_file_done", "strategy": "dynamic",
                    "worker_id": worker_id, "path": path, "elapsed": elapsed
                })

        with files_per_worker_lock:
            files_per_worker[worker_id] = count

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(num_workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    duration = time.time() - start
    return duration, results, files_per_worker