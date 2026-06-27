"""Data update coordinator for eGauge Pro."""

from __future__ import annotations

from dataclasses import dataclass

from egauge_async.exceptions import EgaugeException
from egauge_async.json.client import EgaugeJsonClient
from egauge_async.json.models import RegisterInfo
from httpx import HTTPError

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.httpx_client import get_async_client
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_USE_SSL,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
    DOMAIN,
    LOGGER,
    SCAN_INTERVAL,
)

type EgaugeProConfigEntry = ConfigEntry[EgaugeProCoordinator]


@dataclass
class EgaugeData:
    """Snapshot of eGauge data for one update cycle."""

    register_info: dict[str, RegisterInfo]
    measurements: dict[str, float]  # instantaneous physical values (W, V, A, ...)
    counters: dict[str, float]  # cumulative register counters (W*s for power)


class EgaugeProCoordinator(DataUpdateCoordinator[EgaugeData]):
    """Polls instantaneous values + cumulative counters every cycle."""

    serial_number: str

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            logger=LOGGER,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
            config_entry=config_entry,
        )
        self.client = EgaugeJsonClient(
            host=config_entry.data[CONF_HOST],
            username=config_entry.data[CONF_USERNAME],
            password=config_entry.data[CONF_PASSWORD],
            client=get_async_client(
                hass, verify_ssl=config_entry.data.get(CONF_VERIFY_SSL, True)
            ),
            use_ssl=config_entry.data.get(CONF_USE_SSL, True),
        )
        self.register_info: dict[str, RegisterInfo] = {}

    async def _async_setup(self) -> None:
        """One-time setup: serial number + register metadata."""
        try:
            self.serial_number = await self.client.get_device_serial_number()
            self.register_info = await self.client.get_register_info()
        except (EgaugeException, HTTPError) as err:
            raise ConfigEntryNotReady(f"Cannot reach eGauge: {err}") from err

    async def _async_update_data(self) -> EgaugeData:
        """Fetch instantaneous values + cumulative counters."""
        try:
            measurements = await self.client.get_current_measurements()
            counters = await self.client.get_current_counters()
        except (EgaugeException, HTTPError) as err:
            raise UpdateFailed(f"Error fetching eGauge data: {err}") from err
        return EgaugeData(
            register_info=self.register_info,
            measurements=measurements,
            counters=counters,
        )
