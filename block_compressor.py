"""
Section 8: INTRA-FILE block-level parallel compression, inspired by
how real tools work: pigz (parallel gzip) and filesystems like ZFS
and Btrfs split ONE large file into independent chunks, compress each
chunk simultaneously, then reassemble - a fundamentally different
axis of parallelism than everything else in this project, which has
always parallelized ACROSS many separate files (task parallelism).
This is DATA parallelism: splitting the work WITHIN a single file.

Container format used here (a simplified version of the same idea
pigz/ZFS use): a JSON header line describing each chunk's compressed
size, followed by the concatenated compressed chunk bytes themselves.
Because each chunk is compressed as its OWN independent gzip stream,
each chunk can later be decompressed on its own, in parallel, without
needing to decompress any other chunk first - the same property that
lets pigz decompress files in parallel too, not just compress them.
"""

import os
import json
import time
import threading

from compressor import compress_one_file


def _read_chunk_bytes(file_path, start, length):
    """Reads exactly `length` bytes starting at byte offset `start` -
    used to carve out one contiguous chunk of a large file without
    loading the WHOLE file into memory at once."""
    with open(file_path, "rb") as f:
        f.seek(start)
        return f.read(length)


def split_file_into_chunks(file_path, num_chunks, temp_dir):
    """
    Splits file_path into num_chunks roughly-equal, CONTIGUOUS byte
    ranges, writing each range to its own temp file. Returns the list
    of temp chunk file paths, in order.
    """
    os.makedirs(temp_dir, exist_ok=True)
    total_size = os.path.getsize(file_path)
    chunk_size = total_size // num_chunks

    chunk_paths = []
    for i in range(num_chunks):
        start = i * chunk_size
        # The LAST chunk absorbs any remainder from integer division,
        # so every byte of the original file ends up in exactly one
        # chunk - no bytes silently dropped at the tail end.
        length = (total_size - start) if i == num_chunks - 1 else chunk_size

        chunk_data = _read_chunk_bytes(file_path, start, length)
        chunk_path = os.path.join(temp_dir, f"chunk_{i}")
        with open(chunk_path, "wb") as f:
            f.write(chunk_data)

        chunk_paths.append(chunk_path)

    return chunk_paths


def compress_file_sequential(file_path, output_path):
    """
    BASELINE: compresses the ENTIRE file as a single unit with one
    real fork()+exec()+wait() gzip call - no chunking, no parallelism.
    """
    start = time.time()
    success, _ = compress_one_file(file_path)
    duration = time.time() - start

    generated_gz = file_path + ".gz"
    if success and os.path.exists(generated_gz):
        os.replace(generated_gz, output_path)

    return duration, success


def compress_file_parallel_blocks(file_path, num_workers, temp_dir, output_path, event_queue=None):
    """
    Splits file_path into num_workers chunks, compresses ALL of them
    SIMULTANEOUSLY via real fork()+exec() gzip calls (one real OS
    process per chunk, bounded by a semaphore exactly like the
    inter-file pool built earlier), then reassembles the compressed
    chunks into one container file.
    """
    start = time.time()

    chunk_paths = split_file_into_chunks(file_path, num_workers, temp_dir)

    semaphore = threading.Semaphore(num_workers)
    chunk_compressed_sizes = [None] * num_workers  # pre-sized so results land in the CORRECT order
    results_lock = threading.Lock()

    def worker(chunk_index, chunk_path):
        semaphore.acquire()
        try:
            success, _ = compress_one_file(chunk_path)  # real fork()+exec()+wait() per chunk
            compressed_path = chunk_path + ".gz"
            size = os.path.getsize(compressed_path) if success else 0

            with results_lock:
                chunk_compressed_sizes[chunk_index] = size

            if event_queue:
                event_queue.put({
                    "type": "block_chunk_done", "chunk_index": chunk_index,
                    "compressed_size": size
                })
        finally:
            semaphore.release()

    threads = [threading.Thread(target=worker, args=(i, chunk_paths[i])) for i in range(num_workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Reassemble: JSON header line describing chunk sizes, THEN the
    # concatenated compressed bytes of every chunk, in original order -
    # this is what lets a decompressor later locate any single chunk's
    # bytes without needing to scan the whole file.
    header = {
        "original_size": os.path.getsize(file_path),
        "num_chunks": num_workers,
        "chunk_sizes": chunk_compressed_sizes,
    }
    with open(output_path, "wb") as out:
        header_line = (json.dumps(header) + "\n").encode("utf-8")
        out.write(header_line)
        for i in range(num_workers):
            compressed_chunk_path = chunk_paths[i] + ".gz"
            with open(compressed_chunk_path, "rb") as chunk_f:
                out.write(chunk_f.read())

    # Clean up temp chunk files - they only ever existed to make the
    # real gzip calls possible.
    for chunk_path in chunk_paths:
        for path in (chunk_path, chunk_path + ".gz"):
            if os.path.exists(path):
                os.remove(path)

    duration = time.time() - start
    return duration, output_path


def decompress_file_parallel_blocks(container_path, temp_dir, output_path, event_queue=None):
    """
    Reverses compress_file_parallel_blocks(): reads the JSON header to
    find each chunk's exact byte range within the container, extracts
    each chunk, and decompresses ALL chunks SIMULTANEOUSLY via real
    fork()+exec() gzip -d calls - the same parallel-decompression
    capability real tools like pigz and ZFS/Btrfs have, made possible
    because each chunk was compressed as its own self-contained gzip
    stream in the first place.
    """
    os.makedirs(temp_dir, exist_ok=True)
    start = time.time()

    with open(container_path, "rb") as f:
        header_line = f.readline()
        header = json.loads(header_line.decode("utf-8"))
        chunk_sizes = header["chunk_sizes"]
        num_chunks = header["num_chunks"]

        chunk_gz_paths = []
        for i in range(num_chunks):
            chunk_bytes = f.read(chunk_sizes[i])
            chunk_gz_path = os.path.join(temp_dir, f"restore_chunk_{i}.gz")
            with open(chunk_gz_path, "wb") as chunk_f:
                chunk_f.write(chunk_bytes)
            chunk_gz_paths.append(chunk_gz_path)

    def decompress_one(gz_path):
        """Real fork()+exec()+wait() call to 'gzip -d', decompressing
        one chunk fully independently of all the others."""
        pid = os.fork()
        if pid == 0:
            try:
                os.execvp("gzip", ["gzip", "-d", "-f", gz_path])
            except Exception:
                os._exit(1)
        else:
            _, status = os.waitpid(pid, 0)
            return os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0

    threads_results = [None] * num_chunks

    def worker(index, gz_path):
        threads_results[index] = decompress_one(gz_path)
        if event_queue:
            event_queue.put({"type": "block_decompress_done", "chunk_index": index})

    threads = [threading.Thread(target=worker, args=(i, chunk_gz_paths[i])) for i in range(num_chunks)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Reassemble the original file by concatenating decompressed
    # chunks back together, IN ORDER - since chunks were originally
    # contiguous byte ranges, simple concatenation perfectly
    # reconstructs the exact original file.
    with open(output_path, "wb") as out:
        for i in range(num_chunks):
            decompressed_chunk_path = os.path.join(temp_dir, f"restore_chunk_{i}")
            with open(decompressed_chunk_path, "rb") as chunk_f:
                out.write(chunk_f.read())
            os.remove(decompressed_chunk_path)

    duration = time.time() - start
    success = all(threads_results)
    return duration, success