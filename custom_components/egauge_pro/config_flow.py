"""Config and options flow for eGauge Pro."""

from __future__ import annotations

from typing import Any

from egauge_async.exceptions import EgaugeAuthenticationError, EgaugeException
from egauge_async.json.client import EgaugeJsonClient
from httpx import HTTPError
import voluptuous as vol

from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.httpx_client import get_async_client
import homeassistant.helpers.config_validation as cv

from .const import (
    CONF_HOST,
    CONF_INVERT_SENSORS,
    CONF_PASSWORD,
    CONF_USE_SSL,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
    DOMAIN,
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

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect connection details and validate against the device."""
        errors: dict[str, str] = {}
        if user_input is not None:
            client = EgaugeJsonClient(
                host=user_input[CONF_HOST],
                username=user_input[CONF_USERNAME],
                password=user_input[CONF_PASSWORD],
                client=get_async_client(
                    self.hass, verify_ssl=user_input[CONF_VERIFY_SSL]
                ),
                use_ssl=user_input[CONF_USE_SSL],
            )
            try:
                serial = await client.get_device_serial_number()
            except EgaugeAuthenticationError:
                errors["base"] = "invalid_auth"
            except (EgaugeException, HTTPError):
                errors["base"] = "cannot_connect"
            except ValueError:
                errors[CONF_HOST] = "invalid_host"
            else:
                await self.async_set_unique_id(serial)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=f"eGauge {serial}", data=user_input)
            finally:
                await client.close()

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER, errors=errors
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
        """Manage the inverted-register list."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        registers = sorted(self.config_entry.runtime_data.register_info)
        current = self.config_entry.options.get(CONF_INVERT_SENSORS, [])
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_INVERT_SENSORS, default=current
                ): cv.multi_select(registers)
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
