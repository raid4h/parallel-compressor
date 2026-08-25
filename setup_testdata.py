"""
One-command reproducible test dataset setup. Run this once after
cloning the repo, before running main.py.

WHY THIS EXISTS: testdata/ and testdata_large/ are deliberately
excluded from git (.gitignore) since they're downloaded content, not
source code - this keeps the repo small and avoids committing
someone else's copyrighted-adjacent book text. That means anyone
running this project fresh needs to regenerate
this data first. This script makes that ONE command instead of
several manual steps, and produces the exact same real dataset every
experiment in this project was built and verified against.
"""

import os
import urllib.request
import shutil

# Computed RELATIVE TO THIS SCRIPT's own location, not a hardcoded
# home directory - this makes the script (and the whole project) work
# correctly no matter where the repo gets cloned to, on any machine.
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
TESTDATA_DIR = os.path.join(PROJECT_ROOT, "testdata")
TESTDATA_LARGE_DIR = os.path.join(PROJECT_ROOT, "testdata_large")

# The same 3 real, public-domain books used throughout this project's
# development and verification - downloaded directly from Project
# Gutenberg via Python's standard library urllib, no extra dependency.
BOOKS = {
    "book1.txt": "https://www.gutenberg.org/files/1342/1342-0.txt",   # Pride and Prejudice
    "book2.txt": "https://www.gutenberg.org/files/11/11-0.txt",        # Alice in Wonderland
    "book3.txt": "https://www.gutenberg.org/files/2701/2701-0.txt",    # Moby-Dick
}

COPIES_PER_BOOK = 20  # 3 books x (1 original + 20 copies) = 63 files, matching every result in this project


def download_books(log=print):
    """Downloads each book only if it isn't already present - safe to
    re-run without re-downloading unnecessarily."""
    os.makedirs(TESTDATA_DIR, exist_ok=True)

    for filename, url in BOOKS.items():
        dest_path = os.path.join(TESTDATA_DIR, filename)
        if os.path.exists(dest_path):
            log(f"{filename} already present, skipping download.")
            continue

        log(f"Downloading {filename} from Project Gutenberg...")
        urllib.request.urlretrieve(url, dest_path)


def duplicate_books(log=print):
    """
    Creates COPIES_PER_BOOK duplicates of each book - a real
    multi-file dataset with genuinely UNEVEN content sizes (the 3
    books are different lengths), which is what makes the task-
    decomposition / convoy-effect experiment (Section 4) meaningful
    rather than purely theoretical.
    """
    for filename in BOOKS:
        source_path = os.path.join(TESTDATA_DIR, filename)
        base_name = filename.replace(".txt", "")

        for i in range(1, COPIES_PER_BOOK + 1):
            copy_path = os.path.join(TESTDATA_DIR, f"{base_name}_copy_{i}.txt")
            if not os.path.exists(copy_path):
                shutil.copy(source_path, copy_path)

    total_files = len([f for f in os.listdir(TESTDATA_DIR) if f.endswith(".txt")])
    log(f"testdata/ now contains {total_files} real text files.")


def build_large_file(log=print):
    """
    Concatenates every file in testdata/ into ONE large real file,
    used by Section 8's intra-file block-level compression test -
    still entirely real data, just reshaped into one big file.
    """
    os.makedirs(TESTDATA_LARGE_DIR, exist_ok=True)
    output_path = os.path.join(TESTDATA_LARGE_DIR, "bigfile.txt")

    if os.path.exists(output_path):
        log("testdata_large/bigfile.txt already present, skipping rebuild.")
        return

    txt_files = sorted(f for f in os.listdir(TESTDATA_DIR) if f.endswith(".txt"))
    with open(output_path, "wb") as outfile:
        for filename in txt_files:
            with open(os.path.join(TESTDATA_DIR, filename), "rb") as infile:
                outfile.write(infile.read())

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    log(f"testdata_large/bigfile.txt built ({size_mb:.1f} MB).")


def run_full_setup(log=print):
    """Runs all three setup steps in order - the single function both
    the CLI script and the GUI's 'Download Sample Dataset' button call."""
    log("Step 1/3: Downloading real public-domain books from Project Gutenberg")
    download_books(log)
    log("Step 2/3: Duplicating into a real multi-file test corpus")
    duplicate_books(log)
    log("Step 3/3: Building the large concatenated file for Section 8")
    build_large_file(log)
    log("Setup complete.")


if __name__ == "__main__":
    print("Setting up reproducible test dataset...\n")
    run_full_setup(log=print)
    print("\nYou can now run: python3 main.py")