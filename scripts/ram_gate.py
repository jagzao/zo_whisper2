"""RAM gate for heavy validation (PLV5).

Deterministic measurement of available physical RAM. Heavy validation may
start only when available RAM is strictly greater than 6.0 GiB.

Output JSON on stdout:
    {"available_gib": 7.2, "threshold_gib": 6.0, "heavy_validation": "ALLOWED"}

Exit codes: 0 ALLOWED, 3 DEFERRED_LOW_RAM, 2 measurement/config error.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import sys

THRESHOLD_GIB = 6.0
GIB = 1024 ** 3

ALLOWED = "ALLOWED"
DEFERRED_LOW_RAM = "DEFERRED_LOW_RAM"
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
    """Strict rule: > threshold -> ALLOWED; <= threshold -> DEFERRED_LOW_RAM."""
    return ALLOWED if available_gib > threshold_gib else DEFERRED_LOW_RAM


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
                "heavy_validation": verdict,
            }
        )
    )
    return 0 if verdict == ALLOWED else 3


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    parser = argparse.ArgumentParser(description="PLV5 RAM gate for heavy validation")
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
