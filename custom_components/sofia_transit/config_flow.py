"""Config flow for the Sofia Transit integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required("bus_stop_ids"): str,  # Comma-separated list of bus stop IDs
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the input."""
    bus_stop_ids = data["bus_stop_ids"]
    if not all(id.strip().isdigit() for id in bus_stop_ids.split(",")):
        raise ValueError("Invalid bus stop IDs")
    return {"title": "Sofia Transit", "bus_stop_ids": bus_stop_ids}


class SofiaTransitConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Sofia Transit."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
            except ValueError:
                errors["base"] = "invalid_bus_stop_ids"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title=info["title"], data={"bus_stop_ids": info["bus_stop_ids"]}
                )
        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
