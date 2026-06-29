"""The eGauge Pro integration.

A maintained, JSON-API rewrite of the abandoned `neggert/hass-egauge` custom
integration, run under its own domain (`egauge_pro`) so it does not override the
built-in `egauge`. Adds what core's eGauge integration deliberately omits:
per-circuit energy buckets (today/daily/weekly/monthly/yearly) and per-register
sign inversion.
"""

from __future__ import annotations

from egauge_async.json.models import RegisterType

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.util import slugify

from .const import DOMAIN, LOGGER
from .coordinator import EgaugeProConfigEntry, EgaugeProCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: EgaugeProConfigEntry) -> bool:
    """Set up eGauge Pro from a config entry."""
    coordinator = EgaugeProCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    _canonicalize_entity_ids(hass, coordinator)
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


@callback
def _canonicalize_entity_ids(
    hass: HomeAssistant, coordinator: EgaugeProCoordinator
) -> None:
    """Realign stale entity_ids onto the canonical ``egauge_<slug>`` form.

    On cutover from a prior eGauge integration that used the same
    serial+register unique_id scheme, HA's registry already holds an entry for
    that unique_id under our domain with the OLD auto-generated, device-prefixed
    entity_id (e.g. ``sensor.garage_egauge_egauge_air_conditioning``). HA then
    binds our entity to that stale id instead of the suggested ``egauge_<slug>``
    (``suggested_object_id`` only applies to a FRESH registration). This bit the
    virtual registers added in 0.2.5 — they landed on the old entity_ids while
    physicals (already canonical from an earlier run) were fine.

    For each of OUR registers (matched by unique_id under this domain), rename a
    non-canonical entity_id to ``egauge_<slug>[_energy]`` — but only when the
    target id is FREE (never clobber an existing entity; if the canonical id is
    already held by a leftover/foreign entity, log so the operator can remove
    it). Renaming by unique_id preserves the entity's state history. Idempotent:
    a no-op once everything is canonical, so it's safe to run every setup.
    """
    registry = er.async_get(hass)
    serial = coordinator.serial_number
    for register, info in coordinator.register_info.items():
        slug = slugify(register)
        specs = [(f"{serial}-{register}", f"egauge_{slug}")]
        if info.type is RegisterType.POWER:
            specs.append((f"{serial}-{register}-energy", f"egauge_{slug}_energy"))
        for unique_id, object_id in specs:
            current = registry.async_get_entity_id("sensor", DOMAIN, unique_id)
            if current is None:
                continue
            desired = f"sensor.{object_id}"
            if current == desired:
                continue
            if registry.async_get(desired) is not None:
                LOGGER.warning(
                    "eGauge: cannot rename %s -> %s (the canonical id is held by "
                    "another entity, e.g. a template/helper; retire or rename it "
                    "if you want this counter to take that id)",
                    current,
                    desired,
                )
                continue
            LOGGER.info("eGauge: canonicalizing entity_id %s -> %s", current, desired)
            registry.async_update_entity(current, new_entity_id=desired)


async def async_unload_entry(hass: HomeAssistant, entry: EgaugeProConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.client.close()
    return unloaded


async def _async_update_listener(
    hass: HomeAssistant, entry: EgaugeProConfigEntry
) -> None:
    """Reload when options (e.g. inverted registers) change."""
    await hass.config_entries.async_reload(entry.entry_id)
