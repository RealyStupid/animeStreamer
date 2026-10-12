"""Run the isolated development test suite before starting the API."""

import subprocess
import sys
from pathlib import Path


_API_DIRECTORY = Path(__file__).resolve().parents[1]


def run_development_tests() -> str:
    """Run all API unittest tests and return their output on success."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "unittest",
            "discover",
            "-s",
            "tests",
            "-v",
        ],
        cwd=_API_DIRECTORY,
        capture_output=True,
        text=True,
        check=False,
    )
    output = "\n".join(
        part.strip()
        for part in (result.stdout, result.stderr)
        if part and part.strip()
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Development startup tests failed; refusing to start the API.\n"
            f"{output}"
        )
    return output
