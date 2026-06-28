"""Sensor platform for eGauge Pro."""

from __future__ import annotations

from egauge_async.json.models import RegisterType

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import slugify

from .const import (
    CONF_INVERT_SENSORS,
    CONF_SKIP_ENERGY_COUNTERS,
    ENERGY_UNIT,
    INSTANTANEOUS_DEVICE_CLASS,
    INSTANTANEOUS_UNIT,
    WS_TO_KWH,
)
from .coordinator import EgaugeProConfigEntry, EgaugeProCoordinator
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
            entities.append(EgaugeEnergyCounterSensor(coordinator, name))
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


class EgaugeEnergyCounterSensor(EgaugeProEntity, SensorEntity):
    """Lifetime cumulative energy for a power register (kWh).

    Exposed as ``total_increasing`` so HA long-term statistics + the Energy
    dashboard derive daily/monthly/yearly natively, and ``utility_meter`` can
    cover any explicit cycle sensor — no in-integration period buckets.
    """

    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = ENERGY_UNIT
    _attr_suggested_display_precision = 3

    def __init__(
        self,
        coordinator: EgaugeProCoordinator,
        register: str,
    ) -> None:
        """Initialize a cumulative energy counter."""
        super().__init__(coordinator)
        self._register = register
        self._attr_name = f"{register} energy"
        self._attr_unique_id = f"{coordinator.serial_number}-{register}-energy"

    @property
    def native_value(self) -> float | None:
        """Return the lifetime energy in kWh as a positive, increasing total.

        These counters back ``total_increasing`` energy flows (grid/solar/battery
        directions, per-circuit consumption), each of which accumulates in one
        direction — so the meaningful value is the magnitude; direction is encoded
        by the register identity (``from_grid`` vs ``to_grid`` etc.).

        We take ``abs()`` rather than the user's per-register invert flag: the
        device can report a register's cumulative counter with the OPPOSITE
        polarity to its instantaneous power (e.g. solar reads power +W but counts
        energy −W·s), so a single power-tuned sign can't keep both correct, and a
        negative-trending value is invalid for ``total_increasing`` (HA reads each
        decrease as a reset). The invert flag still governs the instantaneous
        power sensor.
        """
        value = self.coordinator.data.counters.get(self._register)
        if value is None:
            return None
        return abs(value) * WS_TO_KWH

    @property
    def available(self) -> bool:
        """Available once the register's counter is reporting."""
        return super().available and self._register in self.coordinator.data.counters

    @property
    def suggested_object_id(self) -> str | None:
        """Keep the ``egauge_<register>_energy`` entity_id for new installs."""
        return f"egauge_{slugify(self._register)}_energy"
