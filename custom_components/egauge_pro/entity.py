"""Base entity for eGauge Pro."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import EgaugeProCoordinator


class EgaugeProEntity(CoordinatorEntity[EgaugeProCoordinator]):
    """Common base: ties every entity to the one eGauge device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: EgaugeProCoordinator) -> None:
        """Initialize the base entity."""
        super().__init__(coordinator)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.serial_number)},
            name="eGauge",
            manufacturer="eGauge Systems",
            model="Energy Monitor",
            serial_number=coordinator.serial_number,
        )
