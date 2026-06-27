"""Data update coordinator for eGauge Pro."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from egauge_async.exceptions import EgaugeException
from egauge_async.json.client import EgaugeJsonClient
from egauge_async.json.models import RegisterInfo
from httpx import HTTPError

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.httpx_client import get_async_client
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
import homeassistant.util.dt as dt_util

from .const import (
    BUCKET_WINDOWS,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_USE_SSL,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
    DOMAIN,
    HISTORICAL_REFRESH,
    LOGGER,
    SCAN_INTERVAL,
    TODAY,
    WS_TO_KWH,
)

type EgaugeProConfigEntry = ConfigEntry[EgaugeProCoordinator]


@dataclass
class EgaugeData:
    """Snapshot of eGauge data for one update cycle."""

    register_info: dict[str, RegisterInfo]
    measurements: dict[str, float]  # instantaneous physical values (W, V, A, ...)
    buckets: dict[str, dict[str, float]]  # {bucket_key: {register_name: kWh}}


class EgaugeProCoordinator(DataUpdateCoordinator[EgaugeData]):
    """Polls instantaneous power every cycle; refreshes energy buckets slowly."""

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
        self._buckets: dict[str, dict[str, float]] = {}
        self._buckets_at: datetime | None = None

    async def _async_setup(self) -> None:
        """One-time setup: serial number + register metadata."""
        try:
            self.serial_number = await self.client.get_device_serial_number()
            self.register_info = await self.client.get_register_info()
        except (EgaugeException, HTTPError) as err:
            raise ConfigEntryNotReady(f"Cannot reach eGauge: {err}") from err

    async def _async_update_data(self) -> EgaugeData:
        """Fetch instantaneous values, and energy buckets when stale."""
        try:
            measurements = await self.client.get_current_measurements()
            now = dt_util.now()
            if self._needs_bucket_refresh(now):
                self._buckets = await self._fetch_buckets(now)
                self._buckets_at = now
        except (EgaugeException, HTTPError) as err:
            raise UpdateFailed(f"Error fetching eGauge data: {err}") from err
        return EgaugeData(
            register_info=self.register_info,
            measurements=measurements,
            buckets=self._buckets,
        )

    def _needs_bucket_refresh(self, now: datetime) -> bool:
        """Buckets change slowly; refresh on interval or when the local day rolls."""
        if self._buckets_at is None or now - self._buckets_at >= HISTORICAL_REFRESH:
            return True
        return now.date() != self._buckets_at.date()

    async def _fetch_buckets(self, now: datetime) -> dict[str, dict[str, float]]:
        """Per window, diff the cumulative counter at the window start vs now."""
        buckets: dict[str, dict[str, float]] = {}
        for key, window in BUCKET_WINDOWS.items():
            start = dt_util.start_of_local_day() if key == TODAY else now - window
            step = (now - start) or timedelta(seconds=1)
            rows = await self.client.get_historical_counters(
                start_time=start, end_time=now, step=step
            )
            buckets[key] = self._energy_from_rows(rows)
        return buckets

    @staticmethod
    def _energy_from_rows(
        rows: list[dict[str, float | datetime]],
    ) -> dict[str, float]:
        """Energy (kWh) = (latest counter - earliest counter) in W*s, by timestamp.

        Counters are cumulative; we sort by the row 'ts' so we never depend on the
        eGauge's row ordering, and so net registers (which can decrease) are handled.
        """
        if len(rows) < 2:
            return {}
        ordered = sorted(rows, key=lambda r: r["ts"])
        earliest, latest = ordered[0], ordered[-1]
        out: dict[str, float] = {}
        for reg, val in latest.items():
            if reg == "ts" or reg not in earliest:
                continue
            out[reg] = (float(val) - float(earliest[reg])) * WS_TO_KWH
        return out
