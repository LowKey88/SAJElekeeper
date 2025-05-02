# SAJ Monitor - Home Assistant Integration

A Home Assistant custom component for monitoring SAJ solar inverters and battery systems. This integration fetches data from the SAJ cloud API and presents it as sensors within Home Assistant.

## Features

- Monitor SAJ solar inverters and battery systems
- View real-time power generation, grid status, and battery information
- Track daily and total energy production
- Monitor home load power and self-consumption

## Installation

### HACS (Recommended)

1. Make sure [HACS](https://hacs.xyz/) is installed in your Home Assistant instance.
2. Add this repository as a custom repository in HACS:
   - Go to HACS > Integrations > ⋮ > Custom repositories
   - Add `https://github.com/lowkey88/SAJMonitor` as a repository
   - Select "Integration" as the category
3. Click "Download" on the SAJ Monitor integration
4. Restart Home Assistant

### Manual Installation

1. Download the latest release from this repository
2. Create a `custom_components` directory in your Home Assistant configuration directory if it doesn't already exist
3. Extract the `saj_monitor` directory from the release into the `custom_components` directory
4. Restart Home Assistant

## Configuration

1. Go to Home Assistant > Settings > Devices & Services
2. Click "Add Integration" and search for "SAJ Monitor"
3. Follow the configuration steps to add your SAJ Developer API credentials (App ID, App Secret)
4. Add your SAJ devices by providing a name, serial number (SN), plant ID, and device type

## Sensors

The integration provides the following sensors:

- Current Power
- Today's Generation
- Total Generation
- Grid Power
- Grid Status
- Home Load Power
- Self-Consumption Power
- PV Input Power/Voltage/Current (for solar inverters)
- Battery Level/Power/Status/Temperature (for battery systems)
- And more...

## Troubleshooting

If you encounter any issues:

1. Check the Home Assistant logs for error messages
2. Make sure your SAJ Developer API credentials are correct
3. Verify that your device serial numbers and plant IDs are correct
4. Restart Home Assistant after making changes to the integration

## License

This project is licensed under the MIT License - see the LICENSE file for details.
