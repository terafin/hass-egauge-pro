"""The eGauge Pro integration.

A maintained, JSON-API rewrite of the abandoned `neggert/hass-egauge` custom
integration, run under its own domain (`egauge_pro`) so it does not override the
built-in `egauge`. Adds what core's eGauge integration deliberately omits:
per-circuit energy buckets (today/daily/weekly/monthly/yearly) and per-register
sign inversion.
"""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import EgaugeProConfigEntry, EgaugeProCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: EgaugeProConfigEntry) -> bool:
    """Set up eGauge Pro from a config entry."""
    coordinator = EgaugeProCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


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
