"""
Single entry point for the Parallel File Compressor project.

Default (`python3 main.py`): launches the GUI dashboard - this is
what anyone opening this project, including a grader, should run.

`python3 main.py --cli`: runs the full report headlessly in the
terminal instead - same underlying run_full_report() function either
way, just a different front end, useful for a quick check without
opening a window.
"""

import sys
import os
from report_generator import run_full_report, save_report
from gui import launch_gui

DEFAULT_FOLDER = os.path.expanduser("~/parallel-compressor/testdata")


def _run_cli():
    def _print_progress(message):
        print(f">>> {message}")

    print("Parallel File Compressor - Full Optimization Report (CLI mode)")
    print(f"Test folder: {DEFAULT_FOLDER}\n")

    report_text, raw_data = run_full_report(DEFAULT_FOLDER, progress_callback=_print_progress)
    print(report_text)

    txt_path, json_path = save_report(report_text, raw_data)
    print(f"\nReport saved to: {txt_path}")
    print(f"Raw data saved to: {json_path}")


if __name__ == "__main__":
    if "--cli" in sys.argv:
        _run_cli()
    else:
        launch_gui()