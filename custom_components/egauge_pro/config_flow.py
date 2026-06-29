"""Config and options flow for eGauge Pro."""

from __future__ import annotations

from typing import Any

from egauge_async.exceptions import EgaugeAuthenticationError, EgaugeException
from egauge_async.json.client import EgaugeJsonClient
from egauge_async.json.models import RegisterType
from httpx import HTTPError
import voluptuous as vol

from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.httpx_client import get_async_client
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (
    CONF_HOST,
    CONF_INVERT_SENSORS,
    CONF_PASSWORD,
    CONF_SKIP_ENERGY_COUNTERS,
    CONF_USE_SSL,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
    DOMAIN,
    INSTANTANEOUS_UNIT,
)
from .coordinator import EgaugeProConfigEntry

STEP_USER = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Required(CONF_USE_SSL, default=False): bool,
        vol.Required(CONF_VERIFY_SSL, default=True): bool,
    }
)


class EgaugeProConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the eGauge Pro config flow."""

    async def _async_validate(
        self, user_input: dict[str, Any]
    ) -> tuple[str | None, str]:
        """Validate connection details against the device.

        Returns ``(error_key_or_None, serial)``. ``error_key`` keys into the
        flow's ``errors`` dict (``base`` for connection/auth, ``host`` for a
        malformed host); on success it is ``None`` and ``serial`` is set.
        """
        client = EgaugeJsonClient(
            host=user_input[CONF_HOST],
            username=user_input[CONF_USERNAME],
            password=user_input[CONF_PASSWORD],
            client=get_async_client(self.hass, verify_ssl=user_input[CONF_VERIFY_SSL]),
            use_ssl=user_input[CONF_USE_SSL],
        )
        try:
            return None, await client.get_device_serial_number()
        except EgaugeAuthenticationError:
            return "invalid_auth", ""
        except (EgaugeException, HTTPError):
            return "cannot_connect", ""
        except ValueError:
            return "invalid_host", ""
        finally:
            await client.close()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect connection details and validate against the device."""
        errors: dict[str, str] = {}
        if user_input is not None:
            error, serial = await self._async_validate(user_input)
            if error == "invalid_host":
                errors[CONF_HOST] = error
            elif error is not None:
                errors["base"] = error
            else:
                await self.async_set_unique_id(serial)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"eGauge {serial}", data=user_input
                )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER, errors=errors
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change connection details on an existing entry without re-adding it."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            error, serial = await self._async_validate(user_input)
            if error == "invalid_host":
                errors[CONF_HOST] = error
            elif error is not None:
                errors["base"] = error
            else:
                await self.async_set_unique_id(serial)
                self._abort_if_unique_id_mismatch(reason="wrong_device")
                return self.async_update_reload_and_abort(
                    entry, data_updates=user_input
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(STEP_USER, entry.data),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry: EgaugeProConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return EgaugeProOptionsFlow()


class EgaugeProOptionsFlow(OptionsFlow):
    """Let the user pick which registers have their sign inverted."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Offer invert-list config (manual / auto-detect) or the energy-counter set."""
        return self.async_show_menu(
            step_id="init", menu_options=["manual", "auto_detect", "energy_counters"]
        )

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick inverted registers from a searchable chip multi-select."""
        if user_input is not None:
            return self.async_create_entry(
                data={**self.config_entry.options, **user_input}
            )
        current = self.config_entry.options.get(CONF_INVERT_SENSORS, [])
        return self.async_show_form(
            step_id="manual", data_schema=self._invert_schema(current)
        )

    async def async_step_auto_detect(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pre-select registers currently reading negative for the user to confirm."""
        if user_input is not None:
            return self.async_create_entry(
                data={**self.config_entry.options, **user_input}
            )
        return self.async_show_form(
            step_id="auto_detect", data_schema=self._invert_schema(self._suggested())
        )

    async def async_step_energy_counters(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose which power registers to EXCLUDE from energy counters.

        Net / bidirectional registers (net grid/solar/batteries, total usage)
        have an oscillating cumulative counter — invalid for ``total_increasing``
        — so they belong here. Default empty = every power register gets a
        counter (unchanged behaviour).
        """
        if user_input is not None:
            return self.async_create_entry(
                data={**self.config_entry.options, **user_input}
            )
        current = self.config_entry.options.get(CONF_SKIP_ENERGY_COUNTERS, [])
        return self.async_show_form(
            step_id="energy_counters", data_schema=self._skip_counter_schema(current)
        )

    def _skip_counter_schema(self, default: list[str]) -> vol.Schema:
        """Multi-select of power registers to exclude from energy counters."""
        coordinator = self.config_entry.runtime_data
        power = [
            name
            for name, info in coordinator.register_info.items()
            if info.type is RegisterType.POWER
        ]
        options = [
            SelectOptionDict(value=name, label=self._label(name)) for name in power
        ]
        return vol.Schema(
            {
                vol.Optional(
                    CONF_SKIP_ENERGY_COUNTERS, default=default
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=options,
                        multiple=True,
                        mode=SelectSelectorMode.DROPDOWN,
                        sort=False,
                        custom_value=False,
                    )
                )
            }
        )

    def _invert_schema(self, default: list[str]) -> vol.Schema:
        """Build the invert multi-select, options in the eGauge's native order."""
        registers = list(self.config_entry.runtime_data.register_info)
        options = [
            SelectOptionDict(value=name, label=self._label(name)) for name in registers
        ]
        return vol.Schema(
            {
                vol.Optional(CONF_INVERT_SENSORS, default=default): SelectSelector(
                    SelectSelectorConfig(
                        options=options,
                        multiple=True,
                        mode=SelectSelectorMode.DROPDOWN,
                        sort=False,
                        custom_value=False,
                    )
                )
            }
        )

    def _label(self, name: str) -> str:
        """Friendly label hinting the register's current signed value, e.g. ``Grid (-2418 W)``."""
        coordinator = self.config_entry.runtime_data
        info = coordinator.register_info.get(name)
        value = coordinator.data.measurements.get(name) if coordinator.data else None
        if info is None or value is None:
            return name
        unit = INSTANTANEOUS_UNIT.get(info.type)
        return f"{name} ({value:+g} {unit})" if unit else f"{name} ({value:+g})"

    def _suggested(self) -> list[str]:
        """Suggest the invert set: power registers reading negative, plus the current set.

        Uses the coordinator's latest raw measurements (before inversion). Falls back
        to the current set when no data has been polled yet. Additive — never drops a
        register the user already inverted. Returned in native register order.

        EXCLUDES net/bidirectional registers (those the user listed in the
        energy-counter exclude set): they legitimately swing sign, so a transient
        negative reading — e.g. solar power at night — must NOT auto-suggest
        inverting them (that would flip their normal-direction output negative).
        A manual invert of such a register is still preserved.
        """
        coordinator = self.config_entry.runtime_data
        current = set(self.config_entry.options.get(CONF_INVERT_SENSORS, []))
        bidirectional = set(
            self.config_entry.options.get(CONF_SKIP_ENERGY_COUNTERS, [])
        )
        chosen = set(current)
        if coordinator.data is not None:
            info = coordinator.register_info
            chosen |= {
                name
                for name, value in coordinator.data.measurements.items()
                if value < 0
                and name not in bidirectional
                and name in info
                and info[name].type is RegisterType.POWER
            }
        return [name for name in coordinator.register_info if name in chosen]
