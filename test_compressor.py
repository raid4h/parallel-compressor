"""
Standalone sanity check: confirms fork()+exec()+wait() actually works
correctly on your system before we build anything else on top of it.
"""

import os
from compressor import list_files, compress_one_file

# CHANGE THIS to a real folder path with a few files in it. Since we're
# in WSL now, Linux-style paths are used - your Windows files are
# reachable under /mnt/c/... if you want to point at something there,
# but for this test any folder with a few files works fine.
TEST_FOLDER = os.path.expanduser("~/parallel-compressor")  # this project folder itself works as a quick test

if __name__ == "__main__":
    files = list_files(TEST_FOLDER)
    print(f"Found {len(files)} file(s) to compress in {TEST_FOLDER}:")
    for f in files:
        print(f"  - {f}")

    print("\nCompressing each file one at a time...")
    for f in files:
        success, elapsed = compress_one_file(f)
        status = "OK" if success else "FAILED"
        print(f"[{status}] {f}  ({elapsed:.3f}s)")

    print("\nDone. Check the folder - each file should now have a matching .gz version.")