"""Sensor platform for eGauge Pro."""

from __future__ import annotations

from egauge_async.json.models import RegisterType

from dataclasses import dataclass
from typing import Any, Self

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorExtraStoredData,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import slugify

from .const import (
    CONF_INVERT_SENSORS,
    CONF_SKIP_ENERGY_COUNTERS,
    ENERGY_UNIT,
    INSTANTANEOUS_DEVICE_CLASS,
    INSTANTANEOUS_UNIT,
)
from .coordinator import EgaugeProConfigEntry, EgaugeProCoordinator
from .counter import WS_PER_KWH, forward_kwh
from .entity import EgaugeProEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EgaugeProConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create instantaneous sensors for every register + a cumulative energy counter for power."""
    coordinator = entry.runtime_data
    invert: list[str] = entry.options.get(CONF_INVERT_SENSORS, [])
    skip_counters: list[str] = entry.options.get(CONF_SKIP_ENERGY_COUNTERS, [])

    entities: list[SensorEntity] = []
    for name, info in coordinator.register_info.items():
        if info.type in INSTANTANEOUS_DEVICE_CLASS:
            entities.append(
                EgaugeInstantaneousSensor(coordinator, name, info.type, invert)
            )
        # Net/bidirectional registers oscillate -> invalid for total_increasing;
        # operator excludes them via the energy-counter options step.
        if info.type is RegisterType.POWER and name not in skip_counters:
            entities.append(EgaugeEnergyCounterSensor(coordinator, name, invert))
    async_add_entities(entities)


class EgaugeInstantaneousSensor(EgaugeProEntity, SensorEntity):
    """Instantaneous register value (power/voltage/current/temp/humidity/pressure)."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2

    def __init__(
        self,
        coordinator: EgaugeProCoordinator,
        register: str,
        reg_type: RegisterType,
        invert: list[str],
    ) -> None:
        """Initialize an instantaneous sensor."""
        super().__init__(coordinator)
        self._register = register
        self._invert = register in invert
        self._attr_name = register
        self._attr_unique_id = f"{coordinator.serial_number}-{register}"
        self._attr_device_class = INSTANTANEOUS_DEVICE_CLASS[reg_type]
        self._attr_native_unit_of_measurement = INSTANTANEOUS_UNIT[reg_type]

    @property
    def native_value(self) -> float | None:
        """Return the (optionally inverted) instantaneous value."""
        value = self.coordinator.data.measurements.get(self._register)
        if value is None:
            return None
        return -value if self._invert else value

    @property
    def available(self) -> bool:
        """Available only while the register is reporting."""
        return (
            super().available and self._register in self.coordinator.data.measurements
        )

    @property
    def suggested_object_id(self) -> str | None:
        """Keep the ``egauge_`` entity_id prefix for new installs.

        ``has_entity_name=False`` makes the friendly name the bare register, but
        also drops the device prefix HA would otherwise put in the entity_id.
        Overriding this property (the value HA reads at registration) restores
        ``sensor.egauge_<register>``. No effect on already-registered entities —
        their entity_id is sticky (registry keyed by unique_id).
        """
        return f"egauge_{slugify(self._register)}"


@dataclass
class EgaugeCounterExtraStoredData(SensorExtraStoredData):
    """Stored state of an energy counter: its total plus the last raw counter.

    Keeping the last raw counter lets the first update after a restart count
    the energy used while Home Assistant was down.
    """

    last_raw: float | None

    def as_dict(self) -> dict[str, Any]:
        """Return a dict representation of the stored data."""
        data = super().as_dict()
        data["last_raw"] = self.last_raw
        return data

    @classmethod
    def from_dict(cls, restored: dict[str, Any]) -> Self | None:
        """Initialize the stored data from a dict."""
        base = SensorExtraStoredData.from_dict(restored)
        if base is None:
            return None
        last = restored.get("last_raw")
        return cls(
            base.native_value,
            base.native_unit_of_measurement,
            float(last) if isinstance(last, (int, float)) else None,
        )


class EgaugeEnergyCounterSensor(EgaugeProEntity, RestoreSensor):
    """Lifetime energy for a power register (kWh), forward-accumulated.

    Exposed as ``total_increasing`` so HA long-term statistics + the Energy
    dashboard derive daily/monthly/yearly natively. Each step of the meter's
    raw counter is taken in the register's direction of flow (its invert flag)
    and only forward steps are added (see ``counter.py``), so the value never
    decreases whichever side of zero the meter's counter sits on.
    """

    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = ENERGY_UNIT
    _attr_suggested_display_precision = 3

    def __init__(
        self,
        coordinator: EgaugeProCoordinator,
        register: str,
        invert: list[str],
    ) -> None:
        """Initialize a cumulative energy counter."""
        super().__init__(coordinator)
        self._register = register
        self._inverted = register in invert
        self._attr_name = f"{register} energy"
        self._attr_unique_id = f"{coordinator.serial_number}-{register}-energy"
        self._total: float | None = None
        self._last_raw: float | None = None

    async def async_added_to_hass(self) -> None:
        """Continue from the stored total, or start at the meter's magnitude."""
        await super().async_added_to_hass()
        stored = await self.async_get_last_sensor_data()
        if stored is not None and isinstance(stored.native_value, (int, float)):
            self._total = float(stored.native_value)
            extra = await self.async_get_last_extra_data()
            if extra is not None:
                restored = EgaugeCounterExtraStoredData.from_dict(extra.as_dict())
                if restored is not None:
                    self._last_raw = restored.last_raw
        self._update_total()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Fold the new counter reading into the total."""
        self._update_total()
        super()._handle_coordinator_update()

    def _update_total(self) -> None:
        raw = self.coordinator.data.counters.get(self._register)
        if raw is None:
            return
        if self._total is None:
            # No stored total (fresh install, or the first run after upgrading
            # from a release that kept none): start at the meter's lifetime
            # magnitude, the value earlier releases reported, so statistics
            # continue from where they were.
            self._total = abs(raw) / WS_PER_KWH
        else:
            self._total += forward_kwh(self._last_raw, raw, self._inverted)
        self._last_raw = raw

    @property
    def native_value(self) -> float | None:
        """Return the accumulated lifetime energy in kWh."""
        return self._total

    @property
    def extra_restore_state_data(self) -> EgaugeCounterExtraStoredData:
        """Store the total and the last raw counter across restarts."""
        return EgaugeCounterExtraStoredData(
            self._total, self._attr_native_unit_of_measurement, self._last_raw
        )

    @property
    def available(self) -> bool:
        """Available once the register's counter is reporting."""
        return (
            super().available
            and self._total is not None
            and self._register in self.coordinator.data.counters
        )

    @property
    def suggested_object_id(self) -> str | None:
        """Keep the ``egauge_<register>_energy`` entity_id for new installs."""
        return f"egauge_{slugify(self._register)}_energy"
