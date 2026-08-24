"""
Tests intra-file block-level parallel compression on one large real
file, comparing sequential whole-file compression against block-
parallel compression, and verifying the full compress -> decompress
round trip is byte-for-byte correct via checksum.
"""

import os
import hashlib
from block_compressor import (
    compress_file_sequential, compress_file_parallel_blocks, decompress_file_parallel_blocks
)

LARGE_FILE = os.path.expanduser("~/parallel-compressor/testdata_large/bigfile.txt")
TEMP_DIR = os.path.expanduser("~/parallel-compressor/block_temp")
NUM_WORKERS = 8


def file_checksum(path):
    """Real MD5 checksum, used to verify the decompressed output is
    byte-for-byte identical to the original."""
    hasher = hashlib.md5()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


if __name__ == "__main__":
    size_mb = os.path.getsize(LARGE_FILE) / (1024 * 1024)
    print(f"Large file: {LARGE_FILE} ({size_mb:.1f} MB)\n")

    print("=== Sequential (single gzip call on the whole file) ===")
    os.makedirs(TEMP_DIR, exist_ok=True)
    seq_output = os.path.join(TEMP_DIR, "sequential.gz")
    seq_duration, seq_success = compress_file_sequential(LARGE_FILE, seq_output)
    seq_compressed_size = os.path.getsize(seq_output) if seq_success else 0
    print(f"Time: {seq_duration:.3f}s | Success: {seq_success} | "
          f"Compressed size: {seq_compressed_size / (1024*1024):.2f} MB\n")

    print(f"=== Block-parallel ({NUM_WORKERS} chunks, {NUM_WORKERS} real fork()+exec() calls) ===")
    block_output = os.path.join(TEMP_DIR, "parallel_container.bin")
    block_duration, _ = compress_file_parallel_blocks(LARGE_FILE, NUM_WORKERS, TEMP_DIR, block_output)
    block_compressed_size = os.path.getsize(block_output)
    print(f"Time: {block_duration:.3f}s | Container size: {block_compressed_size / (1024*1024):.2f} MB\n")

    speedup = seq_duration / block_duration if block_duration > 0 else 0
    print(f"Speedup from block-level parallelism: {speedup:.2f}x\n")

    print("=== Verifying round-trip correctness (parallel decompression) ===")
    restored_output = os.path.join(TEMP_DIR, "restored.txt")
    decompress_duration, decompress_success = decompress_file_parallel_blocks(
        block_output, TEMP_DIR, restored_output
    )
    print(f"Decompression time: {decompress_duration:.3f}s | Success: {decompress_success}")

    original_checksum = file_checksum(LARGE_FILE)
    restored_checksum = file_checksum(restored_output)
    match = original_checksum == restored_checksum
    print(f"Original checksum:  {original_checksum}")
    print(f"Restored checksum:  {restored_checksum}")
    print(f"Round-trip integrity: {'VERIFIED - byte-for-byte identical' if match else 'MISMATCH - bug!'}")