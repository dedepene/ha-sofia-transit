"""The Sofia Transit integration."""

from __future__ import annotations

import logging

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import (
    async_get_clientsession,
)  # updated import

from .const import DOMAIN
from .coordinator import SofiaTransitUpdateCoordinator
from .helpers import reset_tokens  # new import

_LOGGER = logging.getLogger(__name__)

_PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Sofia Transit from a config entry."""
    session = async_get_clientsession(hass)
    reset_tokens()  # Force a token refresh on startup
    bus_stop_ids = entry.data["bus_stop_ids"].split(",")
    coordinator = SofiaTransitUpdateCoordinator(hass, session, bus_stop_ids)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "coordinator": coordinator,
        "session": session,
    }

    hass.async_create_task(
        hass.config_entries.async_forward_entry_setups(entry, _PLATFORMS)
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, _PLATFORMS)
    if unload_ok:
        data = hass.data[DOMAIN].pop(entry.entry_id)
        await data["session"].close()
    return unload_ok
