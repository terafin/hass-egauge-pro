"""Sensor platform for eGauge Pro."""

from __future__ import annotations

import datetime

from egauge_async.json.models import RegisterType

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
import homeassistant.util.dt as dt_util

from .const import (
    BUCKET_WINDOWS,
    CONF_INVERT_SENSORS,
    ENERGY_UNIT,
    INSTANTANEOUS_DEVICE_CLASS,
    INSTANTANEOUS_UNIT,
    TODAY,
)
from .coordinator import EgaugeProConfigEntry, EgaugeProCoordinator
from .entity import EgaugeProEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EgaugeProConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create instantaneous sensors for every register + energy buckets for power."""
    coordinator = entry.runtime_data
    invert: list[str] = entry.options.get(CONF_INVERT_SENSORS, [])

    entities: list[SensorEntity] = []
    for name, info in coordinator.register_info.items():
        if info.type in INSTANTANEOUS_DEVICE_CLASS:
            entities.append(EgaugeInstantaneousSensor(coordinator, name, info.type, invert))
        if info.type is RegisterType.POWER:
            entities.extend(
                EgaugeBucketSensor(coordinator, name, bucket, invert)
                for bucket in BUCKET_WINDOWS
            )
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
        return super().available and self._register in self.coordinator.data.measurements


class EgaugeBucketSensor(EgaugeProEntity, SensorEntity):
    """Energy consumed by a power register over a window (today/day/week/month/year)."""

    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = ENERGY_UNIT
    _attr_suggested_display_precision = 3

    def __init__(
        self,
        coordinator: EgaugeProCoordinator,
        register: str,
        bucket: str,
        invert: list[str],
    ) -> None:
        """Initialize a bucket (energy) sensor."""
        super().__init__(coordinator)
        self._register = register
        self._bucket = bucket
        self._invert = register in invert
        self._attr_name = f"{bucket} {register}"
        self._attr_unique_id = f"{coordinator.serial_number}-{bucket}-{register}"
        # "today" resets at local midnight -> a proper resetting total the Energy
        # dashboard can consume. Rolling windows are display-only (no state_class).
        if bucket == TODAY:
            self._attr_state_class = SensorStateClass.TOTAL

    @property
    def native_value(self) -> float | None:
        """Return the (optionally inverted) energy for this window."""
        value = self.coordinator.data.buckets.get(self._bucket, {}).get(self._register)
        if value is None:
            return None
        return -value if self._invert else value

    @property
    def last_reset(self) -> datetime.datetime | None:
        """Local midnight for the 'today' total; None otherwise."""
        if self._bucket == TODAY:
            return dt_util.start_of_local_day()
        return None

    @property
    def available(self) -> bool:
        """Available once the bucket has data for this register."""
        return (
            super().available
            and self._register in self.coordinator.data.buckets.get(self._bucket, {})
        )
