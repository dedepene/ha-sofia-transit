import argparse
import asyncio
import json
import sys
from typing import List

import aiohttp
from homeassistant.core import HomeAssistant

from custom_components.sofia_transit.coordinator import SofiaTransitUpdateCoordinator


async def main(stop_ids: List[str]) -> int:
    # Create HA core object with current loop
    hass = HomeAssistant()

    async with aiohttp.ClientSession() as session:
        coordinator = SofiaTransitUpdateCoordinator(hass, session, stop_ids)
        data = await coordinator._async_update_data()

    print(json.dumps(data, ensure_ascii=False, indent=2))
    # Example output: {"lines":[{"line":"1234_M1","next_bus":4}, ...]}
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Sofia Transit coordinator once.")
    parser.add_argument("--stops", required=True, help="Comma-separated stop IDs, e.g. 210,2330")
    args = parser.parse_args()

    ids = [s.strip() for s in args.stops.split(",") if s.strip()]
    if not ids:
        print("No valid stop IDs provided.", file=sys.stderr)
        sys.exit(2)

    sys.exit(asyncio.run(main(ids)))