"""
The actual entry point for this project. Runs the full experiment
suite on real files and produces a comprehensive report, both printed
live and saved as persistent files - this IS the deliverable, not
just a demo.
"""

import os
from report_generator import run_full_report, save_report

TEST_FOLDER = os.path.expanduser("~/parallel-compressor/testdata")


def _print_progress(message):
    print(f">>> {message}")


if __name__ == "__main__":
    print("Parallel File Compressor - Full Optimization Report")
    print(f"Test folder: {TEST_FOLDER}\n")

    report_text, raw_data = run_full_report(TEST_FOLDER, progress_callback=_print_progress)

    print(report_text)

    txt_path, json_path = save_report(report_text, raw_data)
    print(f"\nReport saved to: {txt_path}")
    print(f"Raw data saved to: {json_path}")