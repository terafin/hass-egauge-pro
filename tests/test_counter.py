"""Unit tests for forward-only accumulation of eGauge cumulative counters.

``counter.py`` is free of Home Assistant imports, so it is loaded by path and
tested on its own. The readings are real ones taken 30 s apart from the meter.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "custom_components" / "egauge_pro" / "counter.py"
)
_spec = importlib.util.spec_from_file_location("egauge_counter", _MODULE_PATH)
assert _spec and _spec.loader
counter = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(counter)

forward_kwh = counter.forward_kwh


def test_negative_counter_rising_counts_forward() -> None:
    """House: counter below zero and rising while it consumes 3.2 kW.

    Taking the counter's magnitude made this register run backwards.
    """
    step = forward_kwh(-247_205_814_933, -247_205_717_108, inverted=False)
    assert step > 0
    assert abs(step - 97_825 / 3_600_000) < 1e-12


def test_inverted_positive_counter_falling_counts_forward() -> None:
    """Dryer: inverted register whose counter has crossed above zero."""
    assert forward_kwh(79_108_168_716, 79_108_168_708, inverted=True) > 0


def test_inverted_negative_counter_falling_counts_forward() -> None:
    """Sub Panel: the common inverted case keeps counting forward."""
    step = forward_kwh(-182_797_497_326, -182_797_533_156, inverted=True)
    assert abs(step - 35_830 / 3_600_000) < 1e-12


def test_reverse_step_adds_nothing() -> None:
    """Solar at night: the counter steps backwards, the total holds."""
    assert forward_kwh(125_722_256_406, 125_722_256_006, inverted=False) == 0.0


def test_no_earlier_reading_adds_nothing() -> None:
    assert forward_kwh(None, -247_205_814_933, inverted=False) == 0.0


def test_total_never_decreases_across_a_zero_crossing() -> None:
    """A consuming register whose counter passes through zero keeps rising."""
    readings = [-200.0, -100.0, 0.0, 100.0, 50.0, 300.0]
    total = 0.0
    last = None
    seen = []
    for raw in readings:
        total += forward_kwh(last, raw, inverted=False)
        last = raw
        seen.append(total)
    assert seen == sorted(seen)
    assert abs(total - 550 / 3_600_000) < 1e-12
