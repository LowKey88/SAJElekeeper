# SAJ Monitor - Home Assistant Integration

A Home Assistant custom component for monitoring SAJ solar inverters and battery systems. This integration fetches data from the SAJ cloud API and presents it as sensors within Home Assistant.

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=lowkey88&repository=SAJMonitor&category=integration)

## Features

- Monitor SAJ solar inverters and battery systems
- View real-time power generation, grid status, and battery information
- Track daily and total energy production
- Monitor home load power and self-consumption
- Support for both solar inverters and battery systems
- Automatic detection of nighttime mode for solar inverters
- Environmental impact statistics (CO2 reduction, equivalent trees)

<!-- Add screenshots here once available -->
<!-- 
## Screenshots

![Integration](https://raw.githubusercontent.com/lowkey88/SAJMonitor/main/images/integration.png)
![Sensors](https://raw.githubusercontent.com/lowkey88/SAJMonitor/main/images/sensors.png)
-->

## Installation

### HACS (Recommended)

1. Make sure [HACS](https://hacs.xyz/) is installed in your Home Assistant instance.
2. Click the HACS install button above or add this repository as a custom repository in HACS:
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

## Available Sensors

The integration provides the following sensors:

### Common Sensors (Both Solar and Battery)
- Current Power
- Today's Generation
- Total Generation
- Grid Power
- Grid Status
- Operating Status
- Home Load Power

### Solar Inverter Specific Sensors
- PV1/PV2 Power, Voltage, and Current
- Grid Phase (R, S, T) Power, Voltage, Current, and Frequency
- Inverter Temperature

### Battery System Specific Sensors
- Battery Level
- Battery Power
- Battery Status
- Battery Temperature
- Today's Battery Charge/Discharge
- Total Battery Charge/Discharge
- Battery Efficiency
- Backup Load Power (if available)

### Environmental Impact Sensors
- CO2 Reduction
- Equivalent Trees
- Estimated Annual Production
- Estimated Annual Savings

## Troubleshooting

If you encounter any issues:

1. Check the Home Assistant logs for error messages
2. Make sure your SAJ Developer API credentials are correct
3. Verify that your device serial numbers and plant IDs are correct
4. Restart Home Assistant after making changes to the integration

## Reporting Issues

If you're experiencing problems, please create an issue on GitHub with the following information:
1. A detailed description of the problem
2. Your Home Assistant version
3. The error message from your logs
4. Screenshots if applicable

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.
