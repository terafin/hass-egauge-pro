"""The energy counter sensor never decreases, whichever way the meter counts.

Drives ``EgaugeEnergyCounterSensor`` inside a real Home Assistant with the
meter's counters fed through a stub coordinator; readings are real ones from the
meter taken 30 s apart.
"""

from __future__ import annotations

from types import SimpleNamespace

from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.entity_platform import EntityPlatform
from pytest_homeassistant_custom_component.common import (
    MockEntityPlatform,
    mock_restore_cache_with_extra_data,
)

from custom_components.egauge_pro.sensor import EgaugeEnergyCounterSensor


class _StubCoordinator:
    """Minimal coordinator: a serial, live counters, listener plumbing."""

    def __init__(self, counters: dict[str, float]) -> None:
        self.serial_number = "EG-TEST"
        self.data = SimpleNamespace(counters=counters, measurements={})
        self.last_update_success = True
        self._listeners = []

    def async_add_listener(self, update_callback, context=None):
        self._listeners.append(update_callback)
        return lambda: self._listeners.remove(update_callback)

    def push(self, **counters: float) -> None:
        self.data.counters.update(counters)
        for listener in list(self._listeners):
            listener()


def _sensor(coord: _StubCoordinator, register: str, invert: list[str]):
    try:
        return EgaugeEnergyCounterSensor(coord, register, invert)
    except TypeError:  # releases before the invert-aware counter
        return EgaugeEnergyCounterSensor(coord, register)


async def _add(hass: HomeAssistant, sensor: EgaugeEnergyCounterSensor, entity_id: str):
    sensor.entity_id = entity_id
    platform: EntityPlatform = MockEntityPlatform(hass, domain="sensor", platform_name="egauge_pro")
    await platform.async_add_entities([sensor])
    await hass.async_block_till_done()
    return sensor


async def test_house_counter_below_zero_rises(hass: HomeAssistant) -> None:
    """House consumes 3.2 kW while its raw counter is negative and rising."""
    coord = _StubCoordinator({"House": -247_205_814_933.0})
    sensor = await _add(
        hass, _sensor(coord, "House", []), "sensor.egauge_house_energy"
    )
    first = sensor.native_value
    coord.push(House=-247_205_717_108.0)
    second = sensor.native_value
    assert second > first
    assert abs((second - first) - 97_825 / 3_600_000) < 1e-9


async def test_inverted_dryer_past_zero_rises(hass: HomeAssistant) -> None:
    coord = _StubCoordinator({"Dryer": 79_108_168_716.0})
    sensor = await _add(
        hass, _sensor(coord, "Dryer", ["Dryer"]), "sensor.egauge_dryer_energy"
    )
    first = sensor.native_value
    coord.push(Dryer=79_108_168_000.0)
    assert sensor.native_value > first


async def test_restart_continues_from_stored_total(hass: HomeAssistant) -> None:
    """After a restart the total continues and counts energy used while down."""
    stored = State("sensor.egauge_house_energy", "68668.354")
    mock_restore_cache_with_extra_data(
        hass,
        [
            (
                stored,
                {
                    "native_value": 68668.354,
                    "native_unit_of_measurement": "kWh",
                    "last_raw": -247_205_814_933.0,
                },
            )
        ],
    )
    coord = _StubCoordinator({"House": -247_205_814_933.0 + 3_600_000.0})
    sensor = await _add(
        hass, _sensor(coord, "House", []), "sensor.egauge_house_energy"
    )
    assert abs(sensor.native_value - (68668.354 + 1.0)) < 1e-9


async def test_upgrade_without_stored_raw_holds_then_counts(hass: HomeAssistant) -> None:
    """Upgrading from a release that stored no raw counter keeps the total."""
    mock_restore_cache_with_extra_data(
        hass,
        [
            (
                State("sensor.egauge_house_energy", "68668.354"),
                {"native_value": 68668.354, "native_unit_of_measurement": "kWh"},
            )
        ],
    )
    coord = _StubCoordinator({"House": -247_205_814_933.0})
    sensor = await _add(
        hass, _sensor(coord, "House", []), "sensor.egauge_house_energy"
    )
    assert sensor.native_value == 68668.354
    coord.push(House=-247_205_717_108.0)
    assert sensor.native_value > 68668.354
