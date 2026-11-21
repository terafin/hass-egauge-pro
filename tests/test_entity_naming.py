"""Entity naming: a device-bound entity is rendered "<device> <entity>"."""

from __future__ import annotations

from custom_components.egauge_pro.entity import EgaugeProEntity


class _DummyCoordinator:
    """Enough of a coordinator to construct the base entity."""

    def async_add_listener(self, *args, **kwargs):
        return lambda: None


def _entity() -> EgaugeProEntity:
    return EgaugeProEntity(_DummyCoordinator())


def test_entity_reports_no_device() -> None:
    assert _entity().device_info is None, (
        "the entity must not be device-bound: Home Assistant renders such an "
        "entity as '<device name> <entity name>', which put 'eGauge' in front "
        "of every Energy dashboard label"
    )


def test_entity_keeps_bare_friendly_name() -> None:
    assert _entity().has_entity_name is False, (
        "has_entity_name must stay False so the displayed name is the bare "
        "register rather than the entity-id-shaped fallback"
    )
