"""
A REAL bounded producer-consumer pipeline applied to actual file
discovery and compression - not a simulation. A single PRODUCER thread
walks a real directory tree (potentially very large) and pushes
discovered file paths into a BOUNDED queue.Queue(maxsize=N). Several
CONSUMER worker threads pull paths from that queue and compress each
one via the real fork()+exec()+wait() cycle already built.

Why a BOUNDED queue matters here (not just any queue): for a directory
with millions of files, listing every path into memory before starting
would waste memory and delay the first compression. A bounded queue
gives real backpressure - the producer blocks and stops discovering
new files the moment the queue fills up, until a consumer drains some
of it. This is the textbook Bounded-Buffer problem, but solving a
genuine problem (memory-bounded streaming) instead of simulating one.
"""

import os
import threading
import queue
import time

from compressor import compress_one_file


# A special "poison pill" value pushed onto the queue once for each
# consumer, once the producer has finished walking the directory -
# this is how consumers know there's no more work coming and it's
# safe to exit their loop, rather than blocking forever on an empty
# queue waiting for a next item that will never arrive.
_SENTINEL = None


def _producer(root_folder, work_queue, num_consumers, discovered_count):
    """
    Walks root_folder (RECURSIVELY, unlike our earlier flat listing)
    and pushes every real file's path onto work_queue. Because
    work_queue is BOUNDED, queue.put() below will BLOCK automatically
    once the queue is full - the producer simply pauses until a
    consumer makes room, with zero manual locking needed: queue.Queue
    already handles this internally with a Condition variable, the
    same primitive our earlier hand-rolled Buffer class used.
    """
    for dirpath, _, filenames in os.walk(root_folder):
        for name in filenames:
            if name.endswith(".gz"):
                continue  # skip files we've already compressed in a prior run
            full_path = os.path.join(dirpath, name)
            work_queue.put(full_path)  # BLOCKS here if the queue is full
            discovered_count[0] += 1

    # Push one sentinel per consumer, so every consumer thread gets
    # its own "stop" signal - pushing just one sentinel could let one
    # consumer exit while others starve waiting for a value that was
    # already consumed.
    for _ in range(num_consumers):
        work_queue.put(_SENTINEL)


def _consumer(work_queue, results, results_lock, event_queue, consumer_id):
    """
    Pulls file paths off work_queue and compresses each one, until it
    receives its sentinel (None), at which point it exits cleanly.
    """
    while True:
        path = work_queue.get()  # BLOCKS here if the queue is currently empty

        if path is _SENTINEL:
            return  # producer signaled: no more work is coming

        success, elapsed = compress_one_file(path)

        with results_lock:  # protects the shared results list
            results.append((path, success, elapsed))

        if event_queue:
            event_queue.put({
                "type": "pipeline_file_done", "consumer_id": consumer_id,
                "path": path, "success": success, "elapsed": elapsed
            })


def run_pipeline(root_folder, num_consumers, queue_capacity, event_queue=None):
    """
    Sets up ONE producer thread and num_consumers consumer threads,
    connected by a single BOUNDED queue.Queue(maxsize=queue_capacity),
    runs the whole pipeline to completion, and reports total duration
    plus how many files were discovered and processed.
    """
    start = time.time()

    work_queue = queue.Queue(maxsize=queue_capacity)  # THE bounded buffer
    results = []
    results_lock = threading.Lock()
    discovered_count = [0]  # a mutable single-item list, used as a simple shared counter

    producer_thread = threading.Thread(
        target=_producer, args=(root_folder, work_queue, num_consumers, discovered_count)
    )
    consumer_threads = [
        threading.Thread(target=_consumer, args=(work_queue, results, results_lock, event_queue, i))
        for i in range(num_consumers)
    ]

    producer_thread.start()
    for t in consumer_threads:
        t.start()

    producer_thread.join()
    for t in consumer_threads:
        t.join()

    duration = time.time() - start

    if event_queue:
        event_queue.put({
            "type": "pipeline_done", "duration": duration,
            "discovered": discovered_count[0], "processed": len(results)
        })

    return duration, discovered_count[0], results