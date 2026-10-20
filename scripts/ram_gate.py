"""Resource-aware RAM policy for release validation.

From 4 GiB onward gates may run sequentially; below 6 GiB the runner
rechecks before each gate.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import sys

THRESHOLD_GIB = 6.0
MINIMUM_GIB = 4.0
GIB = 1024 ** 3

STANDARD = "STANDARD"
ALLOWED = STANDARD
LOW_MEMORY_SERIAL = "LOW_MEMORY_SERIAL"
ENV_BLOCKED = "ENV_BLOCKED"
MEASUREMENT_ERROR = "MEASUREMENT_ERROR"


class _MemoryStatusEx(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def _measure_windows() -> int:
    stat = _MemoryStatusEx()
    stat.dwLength = ctypes.sizeof(_MemoryStatusEx)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):  # type: ignore[attr-defined]
        raise OSError("GlobalMemoryStatusEx failed")
    return int(stat.ullAvailPhys)


def _measure_posix() -> int:
    try:
        page_size = os.sysconf("SC_PAGE_SIZE")
        avail_pages = os.sysconf("SC_AVAIL_PAGES")
        return int(page_size) * int(avail_pages)
    except (ValueError, OSError, AttributeError) as exc:
        raise OSError(f"cannot read available memory on this POSIX system: {exc}") from exc


def measure_available_bytes() -> int:
    if os.name == "nt":
        return _measure_windows()
    return _measure_posix()


def evaluate(available_gib: float, threshold_gib: float = THRESHOLD_GIB) -> str:
    """Choose standard, sequential low-memory, or blocked mode."""
    if available_gib < MINIMUM_GIB:
        return ENV_BLOCKED
    if available_gib < threshold_gib:
        return LOW_MEMORY_SERIAL
    return ALLOWED


def run(available_gib_override: float | None = None) -> int:
    try:
        if available_gib_override is not None:
            available_gib = float(available_gib_override)
        else:
            available_gib = measure_available_bytes() / GIB
    except (OSError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "available_gib": None,
                    "threshold_gib": THRESHOLD_GIB,
                    "heavy_validation": MEASUREMENT_ERROR,
                    "error": str(exc),
                }
            )
        )
        return 2

    verdict = evaluate(available_gib)
    print(
        json.dumps(
            {
                "available_gib": round(available_gib, 2),
                "threshold_gib": THRESHOLD_GIB,
                "minimum_gib": MINIMUM_GIB,
                "ram_mode": verdict,
                "heavy_validation": verdict,
            }
        )
    )
    return 3 if verdict == ENV_BLOCKED else 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    parser = argparse.ArgumentParser(description="Resource-aware RAM gate for release validation")
    parser.add_argument(
        "--available-ram-gib",
        type=float,
        default=None,
        help="deterministic override for tests; skips physical measurement",
    )
    args = parser.parse_args(argv)
    return run(args.available_ram_gib)


if __name__ == "__main__":
    sys.exit(main())
