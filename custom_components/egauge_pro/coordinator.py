"""Data update coordinator for eGauge Pro."""

from __future__ import annotations

from dataclasses import dataclass
from xml.etree import ElementTree

import httpx
from egauge_async.exceptions import EgaugeException
from egauge_async.json.client import EgaugeJsonClient
from egauge_async.json.models import RegisterInfo, RegisterType
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
from .virtual import VirtualTerms, compute_virtual, parse_virtual_defs

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
        verify_ssl = config_entry.data.get(CONF_VERIFY_SSL, True)
        self._httpx = get_async_client(hass, verify_ssl=verify_ssl)
        self.client = EgaugeJsonClient(
            host=config_entry.data[CONF_HOST],
            username=config_entry.data[CONF_USERNAME],
            password=config_entry.data[CONF_PASSWORD],
            client=self._httpx,
            use_ssl=config_entry.data.get(CONF_USE_SSL, True),
        )
        # Cumulative counters come from the legacy XML endpoint, not the JSON
        # /api: the JSON counters are unreliable for aggregated / Generation-
        # subtype registers on a multi-eGauge aggregate (sign-flipped and
        # mis-scaled vs the authoritative XML). The XML cumulative is clean.
        scheme = "https" if config_entry.data.get(CONF_USE_SSL, True) else "http"
        self._xml_counter_url = (
            f"{scheme}://{config_entry.data[CONF_HOST]}/cgi-bin/egauge?inst&tot"
        )
        self._xml_auth = httpx.DigestAuth(
            config_entry.data[CONF_USERNAME], config_entry.data[CONF_PASSWORD]
        )
        self.register_info: dict[str, RegisterInfo] = {}
        # Virtual (formula) registers: name -> [(sign, physical-register), ...].
        # Populated from GET /api/config in setup; evaluated each cycle over the
        # physical values we already poll. Empty if the meter has none / the
        # config call is unavailable.
        self._virtual_defs: dict[str, VirtualTerms] = {}

    async def _async_setup(self) -> None:
        """One-time setup: serial number + register metadata + virtual formulas."""
        try:
            self.serial_number = await self.client.get_device_serial_number()
            self.register_info = await self.client.get_register_info()
        except (EgaugeException, HTTPError) as err:
            raise ConfigEntryNotReady(f"Cannot reach eGauge: {err}") from err
        await self._async_load_virtuals()

    async def _async_load_virtuals(self) -> None:
        """Load virtual-register formulas from the WebAPI ``GET /api/config``.

        Best-effort: a meter without virtuals, older firmware, or a missing
        ``view_settings`` right must NOT block setup — on any failure we log and
        continue with physical registers only. Each parsed virtual is added to
        ``register_info`` as a POWER register (synthetic idx, no ``did``) so the
        sensor platform creates an instantaneous sensor + energy counter for it,
        and it flows through the existing invert / skip-counter options exactly
        like a physical register.
        """
        try:
            url = f"{self.client.base_url}/config"
            response = await self.client._get_with_auth(url)  # noqa: SLF001
            response.raise_for_status()
            defs = parse_virtual_defs(response.json())
        except (EgaugeException, HTTPError, ValueError) as err:
            LOGGER.warning(
                "Could not load eGauge virtual registers (continuing with "
                "physical only): %s",
                err,
            )
            return

        self._virtual_defs = defs
        for offset, name in enumerate(defs):
            # Don't shadow a real physical register if the names ever collide.
            if name in self.register_info:
                continue
            self.register_info[name] = RegisterInfo(
                name=name,
                type=RegisterType.POWER,
                idx=-1 - offset,
                did=None,
            )
        if defs:
            LOGGER.debug("Loaded %d eGauge virtual register(s): %s", len(defs), ", ".join(defs))

    async def _async_xml_counters(self) -> dict[str, float]:
        """Cumulative register counters (signed W*s) from the XML endpoint.

        The eGauge XML ``/cgi-bin/egauge?inst&tot`` returns one ``<r n=… t=…>``
        per register with the cumulative value in ``<v>``. This is authoritative
        (clean sign + magnitude) where the JSON ``/api`` counters are not for
        aggregated registers.
        """
        response = await self._httpx.get(self._xml_counter_url, auth=self._xml_auth)
        response.raise_for_status()
        root = ElementTree.fromstring(response.text)
        counters: dict[str, float] = {}
        for register in root.findall("r"):
            name = register.get("n")
            value = register.find("v")
            if name is None or value is None or value.text is None:
                continue
            counters[name] = float(value.text)
        return counters

    async def _async_update_data(self) -> EgaugeData:
        """Fetch instantaneous values (JSON) + cumulative counters (XML)."""
        try:
            measurements = await self.client.get_current_measurements()
            counters = await self._async_xml_counters()
        except (EgaugeException, HTTPError, ElementTree.ParseError) as err:
            raise UpdateFailed(f"Error fetching eGauge data: {err}") from err
        self._apply_virtuals(measurements, counters)
        return EgaugeData(
            register_info=self.register_info,
            measurements=measurements,
            counters=counters,
        )

    def _apply_virtuals(
        self, measurements: dict[str, float], counters: dict[str, float]
    ) -> None:
        """Evaluate each virtual formula over the polled physical values.

        Computes the virtual's instantaneous value from ``measurements`` and its
        cumulative counter from ``counters`` (both in meter-native sign — sign is
        handled per-register by the invert option, same as physical registers).
        A virtual whose components aren't all present that cycle is skipped (no
        partial sum). Mutates the passed dicts in place.
        """
        for name, terms in self._virtual_defs.items():
            value = compute_virtual(terms, measurements)
            if value is not None:
                measurements[name] = value
            counter = compute_virtual(terms, counters)
            if counter is not None:
                counters[name] = counter
