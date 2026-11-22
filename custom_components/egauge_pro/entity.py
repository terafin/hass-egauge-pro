"""Base entity for eGauge Pro."""

from __future__ import annotations

from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import EgaugeProCoordinator


class EgaugeProEntity(CoordinatorEntity[EgaugeProCoordinator]):
    """Common base for every eGauge Pro entity.

    Entities deliberately declare NO ``device_info``.

    Home Assistant composes an entity's displayed name as
    ``"<device name> <entity name>"`` for any entity that belongs to a device,
    regardless of ``has_entity_name``. Declaring the meter as a device therefore
    turned every Energy-dashboard label into "eGauge Pool", "eGauge Jacuzzi",
    "eGauge Hall & Outside Lights", "eGauge Kitchen Lights & GFCI", ... The
    panel is already implied by the dashboard it sits on, so the prefix is pure
    noise on a list of ~40 circuits.

    Without a device the label is the bare register ("Pool"), which is what the
    dashboard should read. ``entity_id`` is unaffected: the registry keys on
    ``unique_id``, so existing installs keep their ids, and ``.sensor`` still
    overrides ``suggested_object_id`` to keep the ``egauge_`` prefix on new
    installs.

    ``_attr_has_entity_name = False`` keeps the friendly name the bare register
    rather than the entity-id-ish fallback.
    """

    _attr_has_entity_name = False

    def __init__(self, coordinator: EgaugeProCoordinator) -> None:
        """Initialize the base entity."""
        super().__init__(coordinator)
