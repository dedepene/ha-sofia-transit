from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

# ...existing code...


class SofiaTransitSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Sofia Transit sensor for a bus line."""

    def __init__(
        self, coordinator, config_entry_id: str, line_id: str, name: str, busstop_begin: str, busstop_end: str
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._line_id = line_id
        self._attr_name = name
        self._busstop_begin = busstop_begin
        self._busstop_end = busstop_end
        # Now include the config entry ID for uniqueness
        self._attr_unique_id = f"{config_entry_id}_{line_id}_sofiatransit"

    @property
    def state(self) -> Any:
        """Return the state of the sensor: minutes until next bus."""
        data = self.coordinator.data
        # Expected data structure: {"lines": [{"line": "1", "next_bus": 3}, ...]}
        if not data:
            return None
        for line in data.get("lines", []):
            if line.get("line") == self._line_id:
                return line.get("next_bus")
        return None

    @property
    def native_value(self) -> Any:
        """Return the native value of the sensor: minutes until next bus."""
        data = self.coordinator.data
        if not data:
            return None
        for line in data.get("lines", []):
            if line.get("line") == self._line_id:
                return line.get("next_bus")
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional sensor attributes."""
        return {"line": self._line_id, "busstop_begin": self._busstop_begin, "busstop_end": self._busstop_end}


# New async_setup_entry function for the sensor platform
async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up sensor entities for Sofia Transit."""
    coordinator = hass.data["sofia_transit"][entry.entry_id]["coordinator"]
    sensors = []
    data = coordinator.data or {}
    for entry_line in data.get("lines", []):
        line_id = entry_line.get("line")
        if line_id:
            sensors.append(
                SofiaTransitSensor(
                    coordinator, entry.entry_id, line_id, f"Sofia Transit {line_id}", entry_line.get("busstop_begin"), entry_line.get("busstop_end")
                )
            )
    async_add_entities(sensors)


# ...existing code...
