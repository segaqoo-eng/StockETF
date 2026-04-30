"""Python tee — runs a Python script as a subprocess, mirroring stdout+stderr
to both the parent's stdout AND a log file.

Replaces PowerShell `Tee-Object` for `update.bat` step 1, which suffered
from PS 5.1's NativeCommandError wrapping when redirecting native-exe stderr.

Usage:
    python scripts/tee.py <script.py> [args...] <log_path>

Last positional arg is the log file path (appended to). Everything before is
the script (and its args) to run.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 3:
        print("Usage: python scripts/tee.py <script.py> [args...] <log_path>",
              file=sys.stderr)
        return 2

    *script_args, log_path = sys.argv[1:]
    log_file = Path(log_path)
    log_file.parent.mkdir(parents=True, exist_ok=True)

    proc = subprocess.Popen(
        [sys.executable, "-u", *script_args],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,    # merge stderr into stdout stream
        text=True,
        encoding="utf-8",
        bufsize=1,                    # line-buffered
    )
    assert proc.stdout is not None    # for type checker
    with log_file.open("a", encoding="utf-8") as log:
        for line in proc.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
            log.write(line)
            log.flush()
    proc.wait()
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
