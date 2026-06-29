"""Virtual (formula) register support for eGauge Pro.

eGauge meters let the operator define *virtual* registers — named formulas that
sum/subtract physical registers (e.g. ``Air Conditioning = AC Compressor + Loft
AC``). The live ``inst`` endpoints the integration polls only return *physical*
registers, so virtuals never become sensors. These helpers parse the formula
definitions from the WebAPI ``GET /api/config`` and evaluate them over the
physical values the coordinator already polls — no extra live endpoint, and an
exact match to what the meter itself reports for the virtual.

Kept free of Home Assistant and network imports so the formula logic is unit
testable on its own.
"""

from __future__ import annotations

from typing import Any

# A parsed virtual: ordered list of (sign, physical-register-name) terms.
VirtualTerms = list[tuple[int, str]]


def parse_virtual_defs(config: Any) -> dict[str, VirtualTerms]:
    """Parse virtual-register formulas from a ``GET /api/config`` response.

    The virtual block lives at ``result.register.virtual`` (with ``register.
    virtual`` / ``virtual`` accepted as fallbacks for envelope variations). Each
    virtual maps to a list of ``{"op": "+"|"-", "register": <physical name>}``
    terms — either directly or wrapped in a ``{"value": [...]}`` object.

    Returns a mapping of virtual name -> ``[(sign, register), ...]`` where sign
    is ``+1`` or ``-1``. Register names are kept verbatim (eGauge virtual names
    can contain spaces and ampersands and must match the physical keys exactly).
    Malformed or empty virtuals are skipped rather than raising — a bad formula
    must not break the whole update.
    """
    virtual = _locate_virtual_block(config)
    if not isinstance(virtual, dict):
        return {}

    defs: dict[str, VirtualTerms] = {}
    for name, raw in virtual.items():
        terms_raw = raw.get("value") if isinstance(raw, dict) else raw
        if not isinstance(terms_raw, list):
            continue
        terms: VirtualTerms = []
        for term in terms_raw:
            if not isinstance(term, dict):
                continue
            register = term.get("register")
            op = term.get("op", "+")
            if not isinstance(register, str) or not register:
                continue
            sign = -1 if op == "-" else 1
            terms.append((sign, register))
        if terms:
            defs[name] = terms
    return defs


def _locate_virtual_block(config: Any) -> Any:
    """Find the ``virtual`` dict across known ``/api/config`` envelope shapes."""
    if not isinstance(config, dict):
        return None
    for path in (("result", "register", "virtual"), ("register", "virtual"), ("virtual",)):
        node: Any = config
        for key in path:
            if isinstance(node, dict) and key in node:
                node = node[key]
            else:
                node = None
                break
        if node is not None:
            return node
    return None


def compute_virtual(terms: VirtualTerms, source: dict[str, float]) -> float | None:
    """Evaluate one virtual's formula over a physical ``register -> value`` map.

    Returns ``sum(sign * source[register])`` over the terms, or ``None`` if any
    referenced physical register is absent from ``source`` (a partial sum would
    silently understate the aggregate, so we emit nothing that cycle instead).
    Works identically for instantaneous values (W) and cumulative counters
    (W·s) — the caller passes whichever map it is aggregating.
    """
    total = 0.0
    for sign, register in terms:
        value = source.get(register)
        if value is None:
            return None
        total += sign * value
    return total
