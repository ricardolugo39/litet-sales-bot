"""Run the established local ETL, then sync its database to Railway."""

import os
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main():
    subprocess.run(
        [sys.executable, "-m", "pipelines.importers.update_all"],
        cwd=PROJECT_ROOT,
        check=True,
    )
    subprocess.run(
        [sys.executable, str(Path(__file__).with_name("sync_database.py"))],
        cwd=PROJECT_ROOT,
        check=True,
    )


if __name__ == "__main__":
    main()
