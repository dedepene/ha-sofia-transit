# Sofia Transit Integration for Home Assistant

This custom integration for Home Assistant provides real-time information about public transportation in Sofia, Bulgaria, using data from the official Sofia Traffic website.

## Features

- Real-time arrival information for buses, trams, trolleybuses, and metro in Sofia
- Support for multiple bus stops
- Updates every 60 seconds
- Sensors showing minutes until next vehicle arrival

## Installation

### HACS Installation (Recommended)

1. Make sure you have [HACS](https://hacs.xyz/) installed in your Home Assistant instance
2. Navigate to HACS in your Home Assistant frontend
3. Click on "Integrations"
4. Click the three-dot menu in the upper right corner
5. Select "Custom repositories"
6. Add the URL of this repository and select "Integration" as the category
7. Click "Add"
8. Find and install the "Sofia Transit" integration

### Manual Installation

1. Copy the `sofia_transit` folder from this repository to your `config/custom_components` directory
2. Restart Home Assistant

## Configuration

1. In Home Assistant, go to **Settings** > **Devices & Services**
2. Click **+ Add Integration** and search for "Sofia Transit"
3. Enter the bus stop IDs as a comma-separated list (e.g., "1234,5678")
   - You can find these IDs in the URL when checking a stop on <a href="https://www.sofiatraffic.bg/bg/public-transport" target="_blank">https://www.sofiatraffic.bg/</a>

## Usage

After configuration, the integration will create sensors for each public transport line at the specified bus stops. Each sensor shows the minutes until the next vehicle arrives.

Sensor naming format:
- `sensor.sofia_transit_stop_id_prefix_number`
  - For example: `sensor.sofia_transit_1234_TM6` for tram line 6 at stop 1234
  - For example: `sensor.sofia_transit_1234_M1` for metro line M1 at stop 1234

### Vehicle Type Prefixes

- `A` - Bus
- `TM` - Tram
- `TB` - Trolleybus
- `M` - Metro
- `N` - Night line

## Troubleshooting

- If you're experiencing issues with the integration, check the Home Assistant logs for error messages
- The integration refreshes its authentication tokens automatically, but sometimes the Sofia Traffic website may have service interruptions

## Contributing

Contributions to improve the integration are welcome! Please feel free to submit pull requests or open issues on the GitHub repository.
