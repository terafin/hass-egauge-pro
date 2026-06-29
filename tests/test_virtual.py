"""Unit tests for eGauge virtual-register formula parsing + evaluation.

The helpers in ``virtual.py`` are deliberately free of Home Assistant and
network imports, so we load the module by path and test the formula logic on
its own — no HA test harness required.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "egauge_pro"
    / "virtual.py"
)
_spec = importlib.util.spec_from_file_location("egauge_virtual", _MODULE_PATH)
assert _spec and _spec.loader
virtual = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(virtual)

parse_virtual_defs = virtual.parse_virtual_defs
compute_virtual = virtual.compute_virtual


# A realistic GET /api/config virtual block (the three load aggregates on the
# main meter), in the documented result.register.virtual envelope.
_CONFIG = {
    "result": {
        "register": {
            "virtual": {
                "Air Conditioning": {
                    "value": [
                        {"op": "+", "register": "AC Compressor"},
                        {"op": "+", "register": "Loft AC"},
                    ]
                },
                "Washer & Dryer": {
                    "value": [
                        {"op": "+", "register": "Washer"},
                        {"op": "+", "register": "Dryer"},
                    ]
                },
            }
        }
    }
}


def test_parse_documented_envelope():
    defs = parse_virtual_defs(_CONFIG)
    assert defs["Air Conditioning"] == [(1, "AC Compressor"), (1, "Loft AC")]
    assert defs["Washer & Dryer"] == [(1, "Washer"), (1, "Dryer")]


def test_parse_handles_bare_list_and_fallback_envelopes():
    # Terms directly under the name (no "value" wrapper) + shallow envelope.
    cfg = {"register": {"virtual": {"X": [{"op": "+", "register": "A"}]}}}
    assert parse_virtual_defs(cfg) == {"X": [(1, "A")]}
    assert parse_virtual_defs({"virtual": {"Y": [{"register": "B"}]}}) == {
        "Y": [(1, "B")]
    }


def test_parse_minus_op_is_negative_sign():
    cfg = {"virtual": {"Net": [{"op": "+", "register": "A"}, {"op": "-", "register": "B"}]}}
    assert parse_virtual_defs(cfg) == {"Net": [(1, "A"), (-1, "B")]}


def test_parse_skips_malformed():
    assert parse_virtual_defs({}) == {}
    assert parse_virtual_defs(None) == {}
    # A virtual with no usable terms is dropped, not emitted empty.
    assert parse_virtual_defs({"virtual": {"Z": [{"op": "+"}]}}) == {}


def test_compute_sum_with_verbatim_names():
    # eGauge load registers report negative (consumption); the raw aggregate is
    # the signed sum — invert is applied per-register downstream, not here.
    source = {"AC Compressor": -2307.0, "Loft AC": -5.0}
    terms = [(1, "AC Compressor"), (1, "Loft AC")]
    assert compute_virtual(terms, source) == -2312.0


def test_compute_respects_signs():
    source = {"A": 100.0, "B": 30.0}
    assert compute_virtual([(1, "A"), (-1, "B")], source) == 70.0


def test_compute_missing_component_returns_none():
    # A partial sum would understate the aggregate, so emit nothing that cycle.
    assert compute_virtual([(1, "A"), (1, "Missing")], {"A": 10.0}) is None


def test_compute_works_for_counters_too():
    # Same logic over cumulative W*s counters.
    counters = {"Washer": 3600000.0, "Dryer": 7200000.0}
    assert compute_virtual([(1, "Washer"), (1, "Dryer")], counters) == 10800000.0
