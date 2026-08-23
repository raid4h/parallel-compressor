"""
Core primitive: compress ONE real file using a genuine fork()+exec()+wait()
sequence - the exact process-creation pattern taught in the course,
implemented directly rather than through a higher-level Python wrapper.

IMPORTANT SAFETY NOTE ON fork() INSIDE A MULTI-THREADED / GUI PROGRAM:
POSIX fork() only duplicates the CALLING thread into the child - any
OTHER threads (including a GUI toolkit's internal threads/locks) simply
vanish in the child, potentially leaving internal state inconsistent.
The standard, safe pattern is: the child must do NOTHING except
immediately call exec() (or exit if exec fails) - no further Python-level
work, no touching the GUI, no logging through shared objects. The moment
exec() succeeds, the process is no longer running Python at all - it's
now running gzip - so any inconsistency from the fork itself becomes
irrelevant. Every function below follows this rule strictly.
"""

import os
import time


def list_files(folder_path):
    """
    Returns full paths of every REAL file directly inside folder_path,
    excluding subfolders and excluding any file that's already a .gz
    (so re-running this script doesn't try to compress its own output).
    """
    paths = []
    for name in os.listdir(folder_path):
        full_path = os.path.join(folder_path, name)
        if os.path.isfile(full_path) and not name.endswith(".gz"):
            paths.append(full_path)
    return paths


def compress_one_file(path):
    """
    Compresses ONE real file by:
      1. fork()  - create a new OS process, an exact duplicate of this one
      2. exec()  - inside the CHILD ONLY, replace its entire process image
                   with the real 'gzip' program
      3. wait()  - inside the PARENT ONLY, block until that specific child
                   process finishes, and retrieve its exit status

    Returns (success: bool, elapsed_seconds: float).
    """
    start = time.time()

    # fork() returns TWICE - once in each process it creates:
    #   - In the PARENT, it returns the new child's process ID (a
    #     positive integer).
    #   - In the CHILD, it returns exactly 0.
    # This return value is the ONLY way to tell which process you're
    # now running as, since both processes continue executing from
    # this exact line onward with otherwise identical memory.
    pid = os.fork()

    if pid == 0:
        # ---- THIS CODE RUNS ONLY IN THE CHILD PROCESS ----
        try:
            # os.execvp() REPLACES this child's entire process image
            # with the 'gzip' program. If this call succeeds, none of
            # the code after it ever runs - the process literally
            # becomes gzip. Flags used:
            #   -f  force: overwrite any existing .gz file from a
            #       previous run of this script
            #   -k  keep: don't delete the original file after
            #       compressing (so we can re-run benchmarks repeatedly)
            os.execvp("gzip", ["gzip", "-f", "-k", path])
        except Exception:
            # If gzip isn't found or exec itself fails for some other
            # reason, we must NOT let this child fall through and
            # continue running as if it were a normal continuation of
            # the parent - that would mean two Python processes both
            # running the rest of this program. os._exit() terminates
            # the child IMMEDIATELY, bypassing normal Python cleanup
            # (which is correct here - the child never finished
            # setting up as a real Python program instance).
            os._exit(1)

    else:
        # ---- THIS CODE RUNS ONLY IN THE PARENT PROCESS ----
        # os.waitpid(pid, 0) blocks the PARENT until the specific
        # child identified by 'pid' finishes, then returns its exit
        # status - this is the real system call that reaps a finished
        # child and prevents it from becoming a "zombie" process.
        _, status = os.waitpid(pid, 0)

        # os.WIFEXITED(status) checks the child terminated normally
        # (not via a crash/signal). os.WEXITSTATUS(status) extracts
        # its actual exit code - 0 conventionally means success.
        success = os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0

        elapsed = time.time() - start
        return success, elapsed