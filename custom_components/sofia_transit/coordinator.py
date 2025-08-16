from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import API_URL, UPDATE_INTERVAL
from .helpers import async_fetch_data_from_sofiatraffic

_LOGGER = logging.getLogger(__name__)


class SofiaTransitUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Class to manage fetching Sofia Transit data."""

    def __init__(self, hass: HomeAssistant, session, bus_stop_ids: list[str]) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="SofiaTransit Update Coordinator",
            update_interval=timedelta(seconds=UPDATE_INTERVAL),
        )
        self.session = session
        self.bus_stop_ids = bus_stop_ids

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch and transform data from Sofia Transit API."""
        all_lines = []
        for stop_id in self.bus_stop_ids:
            try:
                raw_data = await async_fetch_data_from_sofiatraffic(
                    API_URL, self.session, {"stop": stop_id}
                )
                lines = []
                for bus in raw_data.values():
                    details = bus.get("details", [])
                    next_bus = details[0].get("t") if details else None
                    bus_type = bus.get("type")
                    name = bus.get("name")
                    match bus_type:
                        case 1:
                            prefix = "A"  # bus
                        case 2:
                            prefix = "TM"  # tram
                        case 3:
                            # metro
                            prefix = ("" if isinstance(name, str) and name and name.upper().startswith("M") else "M")
                            name = bus.get("route_ext_id")
                        case 4:
                            prefix = "TB"  # trolley
                        case 5:
                            prefix = "N"  # night line
                        case _:
                            prefix = ""
                    full_line = (
                        f"{stop_id}_{prefix}{name}" if prefix else f"{stop_id}_{name}"
                    )
                    busstop_begin, busstop_end = "", ""
                    routename = bus.get('route_name')
                    if isinstance(name, str) and " - " in routename:
                        busstop_begin, busstop_end = routename.split(" - ")
                    lines.append({"line": full_line, "next_bus": next_bus, "busstop_begin": busstop_begin, "busstop_end": busstop_end})
                all_lines.extend(lines)
            except Exception as err:
                _LOGGER.error("Error fetching data for stop %s: %s", stop_id, err)
                continue  # Skip this stop and proceed with others
        if not all_lines:
            raise UpdateFailed("No valid data received for any stop.")
        _LOGGER.debug("Lines received: %s", all_lines)
        return {"lines": all_lines}
