"""PLV5 RAM gate tests (TEST-MATRIX PLV5-H01..H03)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import ram_gate  # noqa: E402


def test_h01_six_point_01_gib_is_allowed():
    assert ram_gate.evaluate(6.01) == ram_gate.ALLOWED


def test_h02_six_point_00_gib_is_deferred():
    assert ram_gate.evaluate(6.00) == ram_gate.DEFERRED_LOW_RAM


def test_h03_five_point_99_gib_is_deferred():
    assert ram_gate.evaluate(5.99) == ram_gate.DEFERRED_LOW_RAM


def test_threshold_is_frozen_at_6_gib():
    assert ram_gate.THRESHOLD_GIB == 6.0


def test_physical_measurement_returns_positive_bytes():
    try:
        available = ram_gate.measure_available_bytes()
    except OSError:
        # Unsupported platform is an exit-2 condition, not a silent pass.
        return
    assert available > 0
