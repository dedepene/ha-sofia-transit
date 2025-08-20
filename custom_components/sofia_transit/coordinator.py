"""Data update coordinator for the Sofia Transit custom component."""

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

    _last_success: dict[str, Any] | None
    _consecutive_failures: int
    _failure_threshold: int

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
        # Keep the last successful payload as a fallback to reduce flapping
        self._last_success = None
        self._consecutive_failures = 0
        # After this many consecutive total failures, surface UpdateFailed
        self._failure_threshold = 3

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch and transform data from Sofia Transit API."""
        all_lines: list[dict[str, Any]] = []

        for stop_id in self.bus_stop_ids:
            try:
                _LOGGER.debug("Fetching data for stop=%s", stop_id)
                raw_data = await async_fetch_data_from_sofiatraffic(
                    API_URL, self.session, {"stop": stop_id}
                )
                lines: list[dict[str, Any]] = []
                for bus in raw_data.values():
                    details = bus.get("details", [])
                    # Collect all arrival times ("t") in details
                    arrivals = [d.get("t") for d in details if "t" in d]
                    next_bus = arrivals[0] if arrivals else None
                    after_next = arrivals[1:] if len(arrivals) > 1 else []
                    bus_type = bus.get("type")
                    name = bus.get("name")
                    match bus_type:
                        case 1:
                            prefix = "A"  # bus
                        case 2:
                            prefix = "TM"  # tram
                        case 3:
                            # metro
                            prefix = (
                                ""
                                if isinstance(name, str)
                                and name
                                and name.upper().startswith("M")
                                else "M"
                            )
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
                    routename = bus.get("route_name")
                    if isinstance(routename, str) and " - " in routename:
                        busstop_begin, busstop_end = routename.split(" - ", 1)
                    lines.append(
                        {
                            "line": full_line,
                            "next_bus": next_bus,
                            "after_next": after_next,
                            "busstop_begin": busstop_begin,
                            "busstop_end": busstop_end,
                        }
                    )
                _LOGGER.debug("Parsed %s lines for stop=%s", len(lines), stop_id)
                all_lines.extend(lines)
            except Exception as err:  # noqa: BLE001 - coordinator boundary
                _LOGGER.error("Error fetching data for stop %s: %s", stop_id, err)
                continue  # Skip this stop and proceed with others

        if not all_lines:
            self._consecutive_failures += 1
            if (
                self._last_success
                and self._consecutive_failures < self._failure_threshold
            ):
                _LOGGER.warning(
                    "No valid data received (fail %s/%s). Serving stale data",
                    self._consecutive_failures,
                    self._failure_threshold,
                )
                return self._last_success
            raise UpdateFailed("No valid data received for any stop.")

        # Success
        self._consecutive_failures = 0
        payload = {"lines": all_lines}
        self._last_success = payload
        _LOGGER.debug("Total lines received: %s", len(all_lines))
        return payload
