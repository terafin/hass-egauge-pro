"""Forward-only energy accumulation for eGauge cumulative counters.

An eGauge cumulative counter is the running integral of its register's signed
power, so it moves in the direction of that power and can sit on either side of
zero. A consuming circuit whose power reads negative counts *down*, a counter
that has crossed zero keeps counting the same way, and solar counts backwards at
night while the inverter idles. Taking the magnitude of the counter therefore
runs any register backwards whose counter is on the far side of zero from its
direction of flow.

The invert flag that makes a register's power read positive is the register's
direction of flow. Each reading's step is taken in that direction and only
forward steps are added, so the total never decreases: a reverse step (solar
standby draw, sensor noise) adds nothing.

Kept free of Home Assistant imports so the logic is unit testable on its own.
"""

from __future__ import annotations

WS_PER_KWH = 3_600_000.0


def forward_kwh(last_raw: float | None, raw: float, inverted: bool) -> float:
    """Energy (kWh) the register moved forward between two raw counter readings.

    ``last_raw`` is None when there is no earlier reading to measure from, and
    the step is zero. Both readings are oriented by the register's current
    invert flag, so changing the flag never turns a stored reading into a jump.
    """
    if last_raw is None:
        return 0.0
    step = raw - last_raw
    if inverted:
        step = -step
    return step / WS_PER_KWH if step > 0 else 0.0
