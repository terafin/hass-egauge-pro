"""The <= 0.2.6 device row, against a real Home Assistant registry."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.egauge_pro import _remove_legacy_device, async_migrate_entry
from custom_components.egauge_pro.const import DOMAIN


async def test_legacy_device_is_removed_and_entities_detached(hass: HomeAssistant):
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)

    dev_reg = dr.async_get(hass)
    device = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "serial-1")},
        name="eGauge",
    )

    ent_reg = er.async_get(hass)
    pool = ent_reg.async_get_or_create(
        "sensor", DOMAIN, "uid-pool", config_entry=entry, device_id=device.id
    )
    jacuzzi = ent_reg.async_get_or_create(
        "sensor", DOMAIN, "uid-jacuzzi", config_entry=entry, device_id=device.id
    )

    _remove_legacy_device(hass, entry)

    assert dev_reg.async_get(device.id) is None
    assert ent_reg.async_get(pool.entity_id).device_id is None
    assert ent_reg.async_get(jacuzzi.entity_id).device_id is None


async def test_no_device_is_a_noop(hass: HomeAssistant):
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)

    _remove_legacy_device(hass, entry)
    _remove_legacy_device(hass, entry)

    assert not dr.async_get(hass).devices


async def test_another_entrys_device_is_left_alone(hass: HomeAssistant):
    mine = MockConfigEntry(domain=DOMAIN, data={})
    mine.add_to_hass(hass)
    other = MockConfigEntry(domain=DOMAIN, data={})
    other.add_to_hass(hass)

    dev_reg = dr.async_get(hass)
    theirs = dev_reg.async_get_or_create(
        config_entry_id=other.entry_id,
        identifiers={(DOMAIN, "serial-2")},
        name="eGauge two",
    )

    _remove_legacy_device(hass, mine)

    assert dev_reg.async_get(theirs.id) is not None


async def test_migration_runs_once(hass: HomeAssistant):
    """A device added after the migration is not removed by a later load."""
    entry = MockConfigEntry(domain=DOMAIN, data={}, version=1)
    entry.add_to_hass(hass)

    dev_reg = dr.async_get(hass)
    legacy = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "serial-1")},
        name="eGauge",
    )

    assert await async_migrate_entry(hass, entry) is True
    assert dev_reg.async_get(legacy.id) is None
    assert entry.version == 2

    attached = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "serial-1-new")},
        name="eGauge attached",
    )

    assert await async_migrate_entry(hass, entry) is True
    assert dev_reg.async_get(attached.id) is not None


async def test_migration_refuses_a_future_version(hass: HomeAssistant):
    entry = MockConfigEntry(domain=DOMAIN, data={}, version=3)
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry) is False
