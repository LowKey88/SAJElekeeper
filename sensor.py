"""Sensor platform for SAJ Solar & Battery Monitor integration."""
import logging
from typing import Dict, List, Any, Optional
import asyncio


# Import the constants first to avoid blocking
from .const import (
    DOMAIN,
    CONF_DEVICES,
    DEVICE_TYPE_SOLAR,
    DEVICE_TYPE_BATTERY,
    SOLAR_ICON,
    BATTERY_ICON,
    POWER_ICON,
    ENERGY_ICON,
    GRID_ICON,
    TEMPERATURE_ICON,
    MONEY_ICON,
    CO2_ICON,
    EFFICIENCY_ICON,
)

# Then import Home Assistant classes
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
)
from homeassistant.const import (
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfFrequency,
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up SAJ sensors based on a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    
    # Make sure we have data
    if not coordinator.last_update_success:
        await coordinator.async_request_refresh()
    
    entities = []
    
    # Add entities for each device
    for device in entry.data[CONF_DEVICES]:
        device_sn = device["sn"]
        device_name = device["name"]
        device_type = device["type"]
        
        # Make sure we have data for this device
        if device_sn not in coordinator.data:
            _LOGGER.warning("No data for device %s (%s), skipping", device_name, device_sn)
            continue
        
        # Create basic info entities
        entities.extend([
            SajPlantNameSensor(coordinator, device_sn, device_name),
            SajCurrentPowerSensor(coordinator, device_sn, device_name),
            SajTodayEnergySensor(coordinator, device_sn, device_name),
            SajTotalEnergySensor(coordinator, device_sn, device_name),
            SajOperatingStatusSensor(coordinator, device_sn, device_name),
            SajOperatingModeSensor(coordinator, device_sn, device_name),
        ])
        
        # Add inverter temperature for solar devices only
        if device_type == DEVICE_TYPE_SOLAR:
            entities.append(SajInverterTemperatureSensor(coordinator, device_sn, device_name))
        
        # Add grid-related entities
        entities.extend([
            SajGridPowerSensor(coordinator, device_sn, device_name),
            SajGridStatusSensor(coordinator, device_sn, device_name),
            SajTodayGridExportSensor(coordinator, device_sn, device_name),
            SajTotalGridExportSensor(coordinator, device_sn, device_name),
        ])
        
        # Add environmental impact sensors
        entities.extend([
            SajCO2ReductionSensor(coordinator, device_sn, device_name),
            SajEquivalentTreesSensor(coordinator, device_sn, device_name),
            SajEstimatedAnnualProductionSensor(coordinator, device_sn, device_name),
            SajEstimatedAnnualSavingsSensor(coordinator, device_sn, device_name),
        ])
        
        # Add load monitoring entities (for all device types)
        entities.extend([
            SajHomeLoadPowerSensor(coordinator, device_sn, device_name),
        ])
        
        # Add solar-specific entities
        if device_type == DEVICE_TYPE_SOLAR:
            # Add PV input entities for active inputs (up to 16 inputs for maximum compatibility)
            for i in range(1, 17):
                # Check if this PV input has data
                device_data = coordinator.data.get(device_sn, {})
                history_data = device_data.get("history_data", {})
                key = f"pv{i}power"
                if key in history_data and float(history_data.get(key, 0)) > 0:
                    entities.extend([
                        SajPVPowerSensor(coordinator, device_sn, device_name, i),
                        SajPVVoltageSensor(coordinator, device_sn, device_name, i),
                        SajPVCurrentSensor(coordinator, device_sn, device_name, i),
                    ])
            
            # Add grid phase information for R6
            device_data = coordinator.data.get(device_sn, {})
            history_data = device_data.get("history_data", {})
            if history_data and "rGridPowerWatt" in history_data:
                for phase in ["r", "s", "t"]:
                    entities.extend([
                        SajGridPhasePowerSensor(coordinator, device_sn, device_name, phase),
                        SajGridPhaseVoltageSensor(coordinator, device_sn, device_name, phase),
                        SajGridPhaseCurrentSensor(coordinator, device_sn, device_name, phase),
                        SajGridPhaseFrequencySensor(coordinator, device_sn, device_name, phase),
                    ])
        
            # Add battery-specific entities
            if device_type == DEVICE_TYPE_BATTERY:
                entities.extend([
                    SajBatteryLevelSensor(coordinator, device_sn, device_name),
                    SajBatteryPowerSensor(coordinator, device_sn, device_name),
                    SajBatteryStatusSensor(coordinator, device_sn, device_name),
                    SajBatteryTemperatureSensor(coordinator, device_sn, device_name),
                    SajTodayBatteryChargeSensor(coordinator, device_sn, device_name),
                    SajTodayBatteryDischargeSensor(coordinator, device_sn, device_name),
                    SajTotalBatteryChargeSensor(coordinator, device_sn, device_name),
                    SajTotalBatteryDischargeSensor(coordinator, device_sn, device_name),
                    SajBatteryRoundTripEfficiencySensor(coordinator, device_sn, device_name),
                    SajTodayLoadEnergySensor(coordinator, device_sn, device_name),
                    SajTotalLoadEnergySensor(coordinator, device_sn, device_name),
                    SajTodayGridImportEnergySensor(coordinator, device_sn, device_name),
                    SajTotalGridImportSensor(coordinator, device_sn, device_name),
                ])
            
            # Add backup load power if available
            device_data = coordinator.data.get(device_sn, {})
            history_data = device_data.get("history_data", {})
            if history_data and "backupTotalLoadPowerWatt" in history_data:
                entities.append(SajBackupLoadPowerSensor(coordinator, device_sn, device_name))
    
    async_add_entities(entities)

class SajBaseSensor(CoordinatorEntity, SensorEntity):
    """Base class for SAJ sensors."""

    def __init__(self, coordinator, device_sn, device_name, name_suffix, unique_id_suffix,
                 icon=None, device_class=None, state_class=None, unit_of_measurement=None):
        """Initialize the sensor."""
        super().__init__(coordinator)
        
        self._device_sn = device_sn
        self._device_name = device_name
        self._attr_name = f"{device_name} {name_suffix}"
        self._attr_unique_id = f"{device_sn}_{unique_id_suffix}"
        self._attr_icon = icon
        self._attr_device_class = device_class
        self._attr_state_class = state_class
        self._attr_native_unit_of_measurement = unit_of_measurement
        
        # Get device data safely
        device_data = self.coordinator.data.get(device_sn, {})
        device_info_wrapper = device_data.get("device_info")
        device_info = device_info_wrapper if isinstance(device_info_wrapper, dict) else {}
        
        # Set up device info
        if device_info and device_info.get("deviceInfo"):
            device_info_data = device_info.get("deviceInfo", {})
            if isinstance(device_info_data, dict):
                model = device_info_data.get("invType", "Unknown")
                self._attr_device_info = DeviceInfo(
                    identifiers={(DOMAIN, device_sn)},
                    name=device_name,
                    manufacturer="SAJ",
                    model=model,
                    sw_version=device_info_data.get("invMFW", "Unknown"),
                )
            else:
                # Fallback to basic device info if deviceInfo is not a dict
                history_data = device_data.get("history_data", {})
                device_sn_value = history_data.get("deviceSn", device_sn)
                module_sn = history_data.get("moduleSn", "Unknown")
                
                self._attr_device_info = DeviceInfo(
                    identifiers={(DOMAIN, device_sn)},
                    name=device_name,
                    manufacturer="SAJ",
                    model=f"SAJ {device_data.get('device_type', 'Device')}",
                    hw_version=module_sn,
                )
        else:
            # Fallback device info using history data
            history_data = device_data.get("history_data", {})
            device_sn_value = history_data.get("deviceSn", device_sn)
            module_sn = history_data.get("moduleSn", "Unknown")
            
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, device_sn)},
                name=device_name,
                manufacturer="SAJ",
                model=f"SAJ {device_data.get('device_type', 'Device')}",
                hw_version=module_sn,
            )

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        if not self.coordinator.last_update_success:
            return False
            
        return self._device_sn in self.coordinator.data
    
    def _get_device_data(self):
        """Get device data from coordinator."""
        return self.coordinator.data.get(self._device_sn, {})
        
    def _get_history_data(self):
        """Get history data from coordinator."""
        device_data = self._get_device_data()
        if not device_data:
            return {}
        history_data = device_data.get("history_data")
        return history_data if isinstance(history_data, dict) else {}
    
    def _get_plant_stats(self):
        """Get plant statistics from coordinator."""
        device_data = self._get_device_data()
        if not device_data:
            return {}
        plant_stats = device_data.get("plant_stats")
        return plant_stats if isinstance(plant_stats, dict) else {}
    
    def _get_processed_data(self):
        """Get processed data from coordinator."""
        device_data = self._get_device_data()
        if not device_data:
            return {}
        processed_data = device_data.get("processed_data")
        return processed_data if isinstance(processed_data, dict) else {}

class SajPlantNameSensor(SajBaseSensor):
    """Sensor for SAJ plant name."""

    def __init__(self, coordinator, device_sn, device_name):
        """Initialize the sensor."""
        super().__init__(
            coordinator=coordinator,
            device_sn=device_sn,
            device_name=device_name,
            name_suffix="Plant Name",
            unique_id_suffix="plant_name",
            icon="mdi:solar-power-variant",
        )

    @property
    def native_value(self):
        """Return the state of the sensor."""
        plant_stats = self._get_plant_stats()
        return plant_stats.get("plantName")

class SajCurrentPowerSensor(SajBaseSensor):
    """Sensor for SAJ current power."""

    def __init__(self, coordinator, device_sn, device_name):
        """Initialize the sensor."""
        super().__init__(
            coordinator=coordinator,
            device_sn=device_sn,
            device_name=device_name,
            name_suffix="Current PV Power",
            unique_id_suffix="current_pv_power",
            icon=POWER_ICON,
            device_class=SensorDeviceClass.POWER,
            state_class=SensorStateClass.MEASUREMENT,
            unit_of_measurement=UnitOfPower.WATT,
        )

    @property
    def native_value(self):
        """Return the state of the sensor."""
        device_data = self._get_device_data()
        
        # First try plant statistics (more accurate)
        plant_stats = self._get_plant_stats()
        power_now = plant_stats.get("powerNow")
        if power_now is not None:
            return float(power_now)
            
        # Fall back to calculated value from processed data
        processed_data = self._get_processed_data()
        calc_power = processed_data.get("total_pv_power_calculated")
        if calc_power is not None:
            return calc_power
            
        # Last resort: try to get from history data
        history_data = self._get_history_data()
        if "totalPVPower" in history_data:
            try:
                return float(history_data["totalPVPower"])
            except (ValueError, TypeError):
                pass
            
        return None

class SajTodayEnergySensor(SajBaseSensor):
    """Sensor for SAJ today's energy production."""

    def __init__(self, coordinator, device_sn, device_name):
        """Initialize the sensor."""
        super().__init__(
            coordinator=coordinator,
            device_sn=device_sn,
            device_name=device_name,
            name_suffix="Today's Generation",
            unique_id_suffix="today_energy",
            icon=ENERGY_ICON,
            device_class=SensorDeviceClass.ENERGY,
            state_class=SensorStateClass.TOTAL_INCREASING,
            unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        )

    @property
    def native_value(self):
        """Return the state of the sensor."""
        device_data = self._get_device_data()
        device_type = device_data.get("device_type")
        processed_data = self._get_processed_data()

        # For battery devices, try processed data which includes realtime data
        if device_type == DEVICE_TYPE_BATTERY and "today_pv_energy" in processed_data:
            return processed_data["today_pv_energy"]

        # Fall back to history data
        history_data = self._get_history_data()
        if "todayPvEnergy" in history_data:
            try:
                return float(history_data["todayPvEnergy"])
            except (ValueError, TypeError):
                pass
            
        # Last resort: plant statistics
        plant_stats = self._get_plant_stats()
        if "todayPvEnergy" in plant_stats:
            try:
                return float(plant_stats["todayPvEnergy"])
            except (ValueError, TypeError):
                pass
            
        return None

class SajTotalEnergySensor(SajBaseSensor):
    """Sensor for SAJ total energy production."""

    def __init__(self, coordinator, device_sn, device_name):
        """Initialize the sensor."""
        super().__init__(
            coordinator=coordinator,
            device_sn=device_sn,
            device_name=device_name,
            name_suffix="Total Generation",
            unique_id_suffix="total_energy",
            icon=ENERGY_ICON,
            device_class=SensorDeviceClass.ENERGY,
            state_class=SensorStateClass.TOTAL,
            unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        )

    @property
    def native_value(self):
        """Return the state of the sensor."""
        device_data = self._get_device_data()
        device_type = device_data.get("device_type")
        
        # For battery devices, try processed data which includes realtime data
        if device_type == DEVICE_TYPE_BATTERY:
            processed_data = self._get_processed_data()
            if "total_pv_energy" in processed_data:
                return processed_data["total_pv_energy"]
        
        # For non-battery devices, try history data first
        history_data = self._get_history_data()
        if "totalPvEnergy" in history_data:
            try:
                return float(history_data["totalPvEnergy"])
            except (ValueError, TypeError):
                pass
            
        # Fall back to plant statistics
        plant_stats = self._get_plant_stats()
        if "totalPvEnergy" in plant_stats:
            try:
                return float(plant_stats["totalPvEnergy"])
            except (ValueError, TypeError):
                pass
            
        return None

class SajOperatingStatusSensor(SajBaseSensor):
    """Sensor for SAJ operating status."""

    def __init__(self, coordinator, device_sn, device_name):
        """Initialize the sensor."""
        super().__init__(
            coordinator=coordinator,
            device_sn=device_sn,
            device_name=device_name,
            name_suffix="Operating Status",
            unique_id_suffix="operating_status",
            icon="mdi:eye",
        )
        
        self._status_descriptions = {
            0: "Initialization",
            1: "Waiting (Standby)",
            2: "Grid connected mode (Generating)",
            3: "Off grid mode (Battery)",
            4: "Grid load mode (Storage)",
            5: "Fault",
            6: "Upgrade",
            7: "Debugging",
            8: "Self inspection",
            9: "Reset"
        }

    @property
    def native_value(self):
        """Return the state of the sensor."""
        device_data = self._get_device_data()
        device_type = device_data.get("device_type")
        
        # For battery devices, try processed data which includes realtime data
        if device_type == DEVICE_TYPE_BATTERY:
            processed_data = self._get_processed_data()
            if "operating_status" in processed_data:
                try:
                    status = int(processed_data["operating_status"])
                    return self._status_descriptions.get(status, f"Unknown status ({status})")
                except (ValueError, TypeError):
                    pass
        
        # Fall back to plant stats for non-battery devices
        plant_stats = self._get_plant_stats()
        if "deviceStatus" in plant_stats:
            try:
                status = int(plant_stats["deviceStatus"])
                return self._status_descriptions.get(status, f"Unknown status ({status})")
            except (ValueError, TypeError):
                pass
            
        return None

class SajOperatingModeSensor(SajBaseSensor):
    """Sensor for SAJ operating mode."""

    def __init__(self, coordinator, device_sn, device_name):
        """Initialize the sensor."""
        super().__init__(
            coordinator=coordinator,
            device_sn=device_sn,
            device_name=device_name,
            name_suffix="Operating Mode",
            unique_id_suffix="operating_mode",
            icon="mdi:cog",
        )
        
        self._mode_descriptions = {
            0: "Unknown",
            1: "Backup Mode",
            2: "Self-Consumption Mode",
            3: "Time-of-Use Mode",
            4: "Export Limitation Mode"
        }

    @property
    def native_value(self):
        """Return the state of the sensor."""
        device_data = self._get_device_data()
        device_type = device_data.get("device_type")
        
        # For battery devices, try processed data which includes realtime data
        if device_type == DEVICE_TYPE_BATTERY:
            processed_data = self._get_processed_data()
            if "operating_mode" in processed_data:
                try:
                    mode = int(processed_data["operating_mode"])
                    return self._mode_descriptions.get(mode, f"Unknown mode ({mode})")
                except (ValueError, TypeError):
                    pass
        
        # Fall back to history data for non-battery devices
        history_data = self._get_history_data()
        if "mpvMode" in history_data:
            try:
                mode = int(history_data["mpvMode"])
                return self._mode_descriptions.get(mode, f"Unknown mode ({mode})")
            except (ValueError, TypeError):
                pass
            
        return None

class SajInverterTemperatureSensor(SajBaseSensor):
    """Sensor for SAJ inverter temperature."""

    def __init__(self, coordinator, device_sn, device_name):
        """Initialize the sensor."""
        super().__init__(
            coordinator=coordinator,
            device_sn=device_sn,
            device_name=device_name,
            name_suffix="Inverter Temperature",
            unique_id_suffix="inverter_temperature",
            icon=TEMPERATURE_ICON,
            device_class=SensorDeviceClass.TEMPERATURE,
            state_class=SensorStateClass.MEASUREMENT,
            unit_of_measurement=UnitOfTemperature.CELSIUS,
        )

    @property
    def native_value(self):
        """Return the state of the sensor."""
        history_data = self._get_history_data()
        if "invTempC" in history_data and history_data["invTempC"] != "0":
            try:
                return float(history_data["invTempC"])
            except (ValueError, TypeError):
                pass
            
        # Try processed data
        processed_data = self._get_processed_data()
        if "inverter_temp" in processed_data:
            return processed_data["inverter_temp"]
            
        return None

class SajGridPowerSensor(SajBaseSensor):
    """Sensor for SAJ grid power."""

    def __init__(self, coordinator, device_sn, device_name):
        """Initialize the sensor."""
        super().__init__(
            coordinator=coordinator,
            device_sn=device_sn,
            device_name=device_name,
            name_suffix="Grid Power",
            unique_id_suffix="grid_power",
            icon=GRID_ICON,
            device_class=SensorDeviceClass.POWER,
            state_class=SensorStateClass.MEASUREMENT,
            unit_of_measurement=UnitOfPower.WATT,
        )

    @property
    def native_value(self):
        """Return the state of the sensor."""
        device_data = self._get_device_data()
        device_type = device_data.get("device_type")
        processed_data = self._get_processed_data()
        
        # For battery devices, try processed data which includes realtime data
        if device_type == DEVICE_TYPE_BATTERY and "grid_power_abs" in processed_data:
            grid_power = processed_data["grid_power_abs"]
            # Note: grid_status_calculated is already set in saj_api.py based on gridDirection
            # Return the raw grid power value
            return grid_power
        
        # Fall back to history data
        history_data = self._get_history_data()
        if "totalGridPowerWatt" in history_data:
            try:
                power = float(history_data["totalGridPowerWatt"])
                if power != 0:
                    # Store grid status for history data too
                    processed_data["grid_status_calculated"] = "importing" if power > 0 else "exporting"
                    return power
            except (ValueError, TypeError):
                pass
            
        return None
        
    @property
    def extra_state_attributes(self):
        """Return the state attributes of the entity."""
        processed_data = self._get_processed_data()
        grid_status = processed_data.get("grid_status_calculated")
        if grid_status:
            return {"status": grid_status}
            
        return {}

class SajGridStatusSensor(SajBaseSensor):
    """Sensor for SAJ grid status."""

    def __init__(self, coordinator, device_sn, device_name):
        """Initialize the sensor."""
        super().__init__(
            coordinator=coordinator,
            device_sn=device_sn,
            device_name=device_name,
            name_suffix="Grid Status",
            unique_id_suffix="grid_status",
            icon=GRID_ICON,
        )

    @property
    def native_value(self):
        """Return the state of the sensor."""
        processed_data = self._get_processed_data()
        return processed_data.get("grid_status_calculated")

class SajTodayGridExportSensor(SajBaseSensor):
    """Sensor for SAJ today's grid export."""

    def __init__(self, coordinator, device_sn, device_name):
        """Initialize the sensor."""
        super().__init__(
            coordinator=coordinator,
            device_sn=device_sn,
            device_name=device_name,
            name_suffix="Today's Grid Export",
            unique_id_suffix="today_grid_export",
            icon=GRID_ICON,
            device_class=SensorDeviceClass.ENERGY,
            state_class=SensorStateClass.TOTAL_INCREASING,
            unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        )

    @property
    def native_value(self):
        """Return the state of the sensor."""
        device_data = self._get_device_data()
        device_type = device_data.get("device_type")
        
        # For battery devices, try processed data which includes realtime data
        if device_type == DEVICE_TYPE_BATTERY:
            processed_data = self._get_processed_data()
            if "today_grid_export_energy" in processed_data:
                return processed_data["today_grid_export_energy"]
        
        # For non-battery devices, try history data first
        history_data = self._get_history_data()
        if "todaySellEnergy" in history_data:
            try:
                return float(history_data["todaySellEnergy"])
            except (ValueError, TypeError):
                pass
            
        # Fall back to plant statistics
        plant_stats = self._get_plant_stats()
        if "todaySellEnergy" in plant_stats:
            try:
                return float(plant_stats["todaySellEnergy"])
            except (ValueError, TypeError):
                pass
            
        return None

class SajTotalGridExportSensor(SajBaseSensor):
    """Sensor for SAJ total grid export."""

    def __init__(self, coordinator, device_sn, device_name):
        """Initialize the sensor."""
        super().__init__(
            coordinator=coordinator,
            device_sn=device_sn,
            device_name=device_name,
            name_suffix="Total Grid Export",
            unique_id_suffix="total_grid_export",
            icon=GRID_ICON,
            device_class=SensorDeviceClass.ENERGY,
            state_class=SensorStateClass.TOTAL,
            unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        )

    @property
    def native_value(self):
        """Return the state of the sensor."""
        device_data = self._get_device_data()
        device_type = device_data.get("device_type")
        
        # For battery devices, try processed data which includes realtime data
        if device_type == DEVICE_TYPE_BATTERY:
            processed_data = self._get_processed_data()
            if "total_grid_export" in processed_data:
                return processed_data["total_grid_export"]
        
        # For non-battery devices, try history data first
        history_data = self._get_history_data()
        if "totalSellEnergy" in history_data:
            try:
                return float(history_data["totalSellEnergy"])
            except (ValueError, TypeError):
                pass
            
        # Fall back to plant statistics
        plant_stats = self._get_plant_stats()
        if "totalSellEnergy" in plant_stats:
            try:
                return float(plant_stats["totalSellEnergy"])
            except (ValueError, TypeError):
                pass
            
        return None

class SajPVPowerSensor(SajBaseSensor):
    """Sensor for SAJ PV input power."""

    def __init__(self, coordinator, device_sn, device_name, pv_input):
        """Initialize the sensor."""
        self._pv_input = pv_input
        super().__init__(
            coordinator=coordinator,
            device_sn=device_sn,
            device_name=device_name,
            name_suffix=f"PV{pv_input} Power",
            unique_id_suffix=f"pv{pv_input}_power",
            icon=SOLAR_ICON,
            device_class=SensorDeviceClass.POWER,
            state_class=SensorStateClass.MEASUREMENT,
            unit_of_measurement=UnitOfPower.WATT,
        )

    @property
    def native_value(self):
        """Return the state of the sensor."""
        history_data = self._get_history_data()
        power_key = f"pv{self._pv_input}power"
        
        if power_key in history_data:
            try:
                return float(history_data[power_key])
            except (ValueError, TypeError):
                pass
            
        # Try processed data
        processed_data = self._get_processed_data()
        if f"pv{self._pv_input}_power" in processed_data:
            return processed_data[f"pv{self._pv_input}_power"]
            
        return None
        
    @property
    def available(self):
        """Return if entity is available."""
        if not super().available:
            return False
            
        # Get the PV power value
        history_data = self._get_history_data()
        power_key = f"pv{self._pv_input}power"
        
        if power_key in history_data:
            try:
                power_value = float(history_data[power_key])
                # Only consider available if power is greater than 0
                return power_value > 0
            except (ValueError, TypeError):
                pass
                
        # Try processed data
        processed_data = self._get_processed_data()
        if f"pv{self._pv_input}_power" in processed_data:
            return processed_data[f"pv{self._pv_input}_power"] > 0
            
        return False

class SajPVVoltageSensor(SajBaseSensor):
    """Sensor for SAJ PV input voltage."""

    def __init__(self, coordinator, device_sn, device_name, pv_input):
        """Initialize the sensor."""
        self._pv_input = pv_input
        super().__init__(
            coordinator=coordinator,
            device_sn=device_sn,
            device_name=device_name,
            name_suffix=f"PV{pv_input} Voltage",
            unique_id_suffix=f"pv{pv_input}_voltage",
            icon=SOLAR_ICON,
            device_class=SensorDeviceClass.VOLTAGE,
            state_class=SensorStateClass.MEASUREMENT,
            unit_of_measurement=UnitOfElectricPotential.VOLT,
        )

    @property
    def native_value(self):
        """Return the state of the sensor."""
        history_data = self._get_history_data()
        voltage_key = f"pv{self._pv_input}volt"
        
        if voltage_key in history_data:
            try:
                return float(history_data[voltage_key])
            except (ValueError, TypeError):
                pass
            
        return None
        
    @property
    def available(self):
        """Return if entity is available."""
        if not super().available:
            return False
            
        # Only consider available if the PV input has actual power
        history_data = self._get_history_data()
        power_key = f"pv{self._pv_input}power"
        
        if power_key in history_data:
            try:
                power_value = float(history_data[power_key])
                return power_value > 0
            except (ValueError, TypeError):
                pass
                
        return False

class SajPVCurrentSensor(SajBaseSensor):
    """Sensor for SAJ PV input current."""

    def __init__(self, coordinator, device_sn, device_name, pv_input):
        """Initialize the sensor."""
        self._pv_input = pv_input
        super().__init__(
            coordinator=coordinator,
            device_sn=device_sn,
            device_name=device_name,
            name_suffix=f"PV{pv_input} Current",
            unique_id_suffix=f"pv{self._pv_input}_current",
            icon=SOLAR_ICON,
            device_class=SensorDeviceClass.CURRENT,
            state_class=SensorStateClass.MEASUREMENT,
            unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        )

    @property
    def native_value(self):
        """Return the state of the sensor."""
        history_data = self._get_history_data()
        current_key = f"pv{self._pv_input}curr"
        
        if current_key in history_data:
            try:
                return float(history_data[current_key])
            except (ValueError, TypeError):
                pass
            
        return None
        
    @property
    def available(self):
        """Return if entity is available."""
        if not super().available:
            return False
            
        # Only consider available if the PV input has actual power
        history_data = self._get_history_data()
        power_key = f"pv{self._pv_input}power"
        
        if power_key in history_data:
            try:
                power_value = float(history_data[power_key])
                return power_value > 0
            except (ValueError, TypeError):
                pass
                
        return False

class SajGridPhasePowerSensor(SajBaseSensor):
    """Sensor for SAJ grid phase power."""

    def __init__(self, coordinator, device_sn, device_name, phase):
        """Initialize the sensor."""
        self._phase = phase
        phase_name = {"r": "R", "s": "S", "t": "T"}[phase]
        super().__init__(
            coordinator=coordinator,
            device_sn=device_sn,
            device_name=device_name,
            name_suffix=f"Grid {phase_name}-Phase Power",
            unique_id_suffix=f"grid_{phase}_phase_power",
            icon=GRID_ICON,
            device_class=SensorDeviceClass.POWER,
            state_class=SensorStateClass.MEASUREMENT,
            unit_of_measurement=UnitOfPower.WATT,
        )

    @property
    def native_value(self):
        """Return the state of the sensor."""
        history_data = self._get_history_data()
        power_key = f"{self._phase}GridPowerWatt"
        
        if power_key in history_data:
            try:
                return float(history_data[power_key])
            except (ValueError, TypeError):
                pass
            
        # Try processed data
        processed_data = self._get_processed_data()
        if f"{self._phase}_phase_power" in processed_data:
            return processed_data[f"{self._phase}_phase_power"]
            
        return None
        
    @property
    def available(self):
        """Return if entity is available."""
        if not super().available:
            return False
            
        history_data = self._get_history_data()
        power_key = f"{self._phase}GridPowerWatt"
        
        return power_key in history_data and history_data[power_key] != "0"

class SajGridPhaseVoltageSensor(SajBaseSensor):
    """Sensor for SAJ grid phase voltage."""

    def __init__(self, coordinator, device_sn, device_name, phase):
        """Initialize the sensor."""
        self._phase = phase
        phase_name = {"r": "R", "s": "S", "t": "T"}[phase]
        super().__init__(
            coordinator=coordinator,
            device_sn=device_sn,
            device_name=device_name,
            name_suffix=f"Grid {phase_name}-Phase Voltage",
            unique_id_suffix=f"grid_{phase}_phase_voltage",
            icon=GRID_ICON,
            device_class=SensorDeviceClass.VOLTAGE,
            state_class=SensorStateClass.MEASUREMENT,
            unit_of_measurement=UnitOfElectricPotential.VOLT,
        )

    @property
    def native_value(self):
        """Return the state of the sensor."""
        history_data = self._get_history_data()
        voltage_key = f"{self._phase}GridVolt"
        
        if voltage_key in history_data:
            try:
                return float(history_data[voltage_key])
            except (ValueError, TypeError):
                pass
            
        return None
        
    @property
    def available(self):
        """Return if entity is available."""
        if not super().available:
            return False
            
        history_data = self._get_history_data()
        voltage_key = f"{self._phase}GridVolt"
        
        return voltage_key in history_data and history_data[voltage_key] != "0"

class SajGridPhaseCurrentSensor(SajBaseSensor):
    """Sensor for SAJ grid phase current."""

    def __init__(self, coordinator, device_sn, device_name, phase):
        """Initialize the sensor."""
        self._phase = phase
        phase_name = {"r": "R", "s": "S", "t": "T"}[phase]
        super().__init__(
            coordinator=coordinator,
            device_sn=device_sn,
            device_name=device_name,
            name_suffix=f"Grid {phase_name}-Phase Current",
            unique_id_suffix=f"grid_{phase}_phase_current",
            icon=GRID_ICON,
            device_class=SensorDeviceClass.CURRENT,
            state_class=SensorStateClass.MEASUREMENT,
            unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        )

    @property
    def native_value(self):
        """Return the state of the sensor."""
        history_data = self._get_history_data()
        current_key = f"{self._phase}GridCurr"
        
        if current_key in history_data:
            try:
                return float(history_data[current_key])
            except (ValueError, TypeError):
                pass
            
        return None
        
    @property
    def available(self):
        """Return if entity is available."""
        if not super().available:
            return False
            
        history_data = self._get_history_data()
        current_key = f"{self._phase}GridCurr"
        
        return current_key in history_data and history_data[current_key] != "0"

class SajGridPhaseFrequencySensor(SajBaseSensor):
    """Sensor for SAJ grid phase frequency."""

    def __init__(self, coordinator, device_sn, device_name, phase):
        """Initialize the sensor."""
        self._phase = phase
        phase_name = {"r": "R", "s": "S", "t": "T"}[phase]
        super().__init__(
            coordinator=coordinator,
            device_sn=device_sn,
            device_name=device_name,
            name_suffix=f"Grid {phase_name}-Phase Frequency",
            unique_id_suffix=f"grid_{phase}_phase_frequency",
            icon=GRID_ICON,
            device_class=SensorDeviceClass.FREQUENCY,
            state_class=SensorStateClass.MEASUREMENT,
            unit_of_measurement=UnitOfFrequency.HERTZ,
        )

    @property
    def native_value(self):
        """Return the state of the sensor."""
        history_data = self._get_history_data()
        freq_key = f"{self._phase}GridFreq"
        
        if freq_key in history_data:
            try:
                return float(history_data[freq_key])
            except (ValueError, TypeError):
                pass
            
        return None
        
    @property
    def available(self):
        """Return if entity is available."""
        if not super().available:
            return False
            
        history_data = self._get_history_data()
        freq_key = f"{self._phase}GridFreq"
        
        return freq_key in history_data and history_data[freq_key] != "0"

class SajBatteryLevelSensor(SajBaseSensor):
    """Sensor for SAJ battery level."""

    def __init__(self, coordinator, device_sn, device_name):
        """Initialize the sensor."""
        super().__init__(
            coordinator=coordinator,
            device_sn=device_sn,
            device_name=device_name,
            name_suffix="Battery Level",
            unique_id_suffix="battery_level",
            icon=BATTERY_ICON,
            device_class=SensorDeviceClass.BATTERY,
            state_class=SensorStateClass.MEASUREMENT,
            unit_of_measurement=PERCENTAGE,
        )

    @property
    def native_value(self):
        """Return the state of the sensor."""
        processed_data = self._get_processed_data()
        return processed_data.get("battery_level")

class SajBatteryPowerSensor(SajBaseSensor):
    """Sensor for SAJ battery power."""

    def __init__(self, coordinator, device_sn, device_name):
        """Initialize the sensor."""
        super().__init__(
            coordinator=coordinator,
            device_sn=device_sn,
            device_name=device_name,
            name_suffix="Battery Power",
            unique_id_suffix="battery_power",
            icon=BATTERY_ICON,
            device_class=SensorDeviceClass.POWER,
            state_class=SensorStateClass.MEASUREMENT,
            unit_of_measurement=UnitOfPower.WATT,
        )

    @property
    def native_value(self):
        """Return the state of the sensor."""
        processed_data = self._get_processed_data()
        
        if "battery_power_abs" in processed_data:
            # Apply sign based on battery status
            power = processed_data["battery_power_abs"]
            status = processed_data.get("battery_status_calculated", "")
            return power if status == "Discharging" else -power if status == "Charging" else 0
            
        return None
        
    @property
    def extra_state_attributes(self):
        """Return the state attributes of the entity."""
        processed_data = self._get_processed_data()
        battery_status = processed_data.get("battery_status_calculated")
        if battery_status:
            return {"status": battery_status}
            
        return {}

class SajBatteryStatusSensor(SajBaseSensor):
    """Sensor for SAJ battery status."""

    def __init__(self, coordinator, device_sn, device_name):
        """Initialize the sensor."""
        super().__init__(
            coordinator=coordinator,
            device_sn=device_sn,
            device_name=device_name,
            name_suffix="Battery Status",
            unique_id_suffix="battery_status",
            icon=BATTERY_ICON,
        )

    @property
    def native_value(self):
        """Return the state of the sensor."""
        processed_data = self._get_processed_data()
        return processed_data.get("battery_status_calculated")

class SajBatteryTemperatureSensor(SajBaseSensor):
    """Sensor for SAJ battery temperature."""

    def __init__(self, coordinator, device_sn, device_name):
        """Initialize the sensor."""
        super().__init__(
            coordinator=coordinator,
            device_sn=device_sn,
            device_name=device_name,
            name_suffix="Battery Temperature",
            unique_id_suffix="battery_temperature",
            icon=TEMPERATURE_ICON,
            device_class=SensorDeviceClass.TEMPERATURE,
            state_class=SensorStateClass.MEASUREMENT,
            unit_of_measurement=UnitOfTemperature.CELSIUS,
        )

    @property
    def native_value(self):
        """Return the state of the sensor."""
        processed_data = self._get_processed_data()
        return processed_data.get("battery_temp")

class SajTodayBatteryChargeSensor(SajBaseSensor):
    """Sensor for SAJ today's battery charge."""

    def __init__(self, coordinator, device_sn, device_name):
        """Initialize the sensor."""
        super().__init__(
            coordinator=coordinator,
            device_sn=device_sn,
            device_name=device_name,
            name_suffix="Today's Battery Charge",
            unique_id_suffix="today_battery_charge",
            icon=BATTERY_ICON,
            device_class=SensorDeviceClass.ENERGY,
            state_class=SensorStateClass.TOTAL_INCREASING,
            unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        )

    @property
    def native_value(self):
        """Return the state of the sensor."""
        processed_data = self._get_processed_data()
        return processed_data.get("today_battery_charge")

class SajTodayBatteryDischargeSensor(SajBaseSensor):
    """Sensor for SAJ today's battery discharge."""

    def __init__(self, coordinator, device_sn, device_name):
        """Initialize the sensor."""
        super().__init__(
            coordinator=coordinator,
            device_sn=device_sn,
            device_name=device_name,
            name_suffix="Today's Battery Discharge",
            unique_id_suffix="today_battery_discharge",
            icon=BATTERY_ICON,
            device_class=SensorDeviceClass.ENERGY,
            state_class=SensorStateClass.TOTAL_INCREASING,
            unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        )

    @property
    def native_value(self):
        """Return the state of the sensor."""
        processed_data = self._get_processed_data()
        return processed_data.get("today_battery_discharge")

class SajTotalBatteryChargeSensor(SajBaseSensor):
    """Sensor for SAJ total battery charge."""

    def __init__(self, coordinator, device_sn, device_name):
        """Initialize the sensor."""
        super().__init__(
            coordinator=coordinator,
            device_sn=device_sn,
            device_name=device_name,
            name_suffix="Total Battery Charge",
            unique_id_suffix="total_battery_charge",
            icon=BATTERY_ICON,
            device_class=SensorDeviceClass.ENERGY,
            state_class=SensorStateClass.TOTAL,
            unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        )

    @property
    def native_value(self):
        """Return the state of the sensor."""
        processed_data = self._get_processed_data()
        return processed_data.get("total_battery_charge")

class SajTotalBatteryDischargeSensor(SajBaseSensor):
    """Sensor for SAJ total battery discharge."""

    def __init__(self, coordinator, device_sn, device_name):
        """Initialize the sensor."""
        super().__init__(
            coordinator=coordinator,
            device_sn=device_sn,
            device_name=device_name,
            name_suffix="Total Battery Discharge",
            unique_id_suffix="total_battery_discharge",
            icon=BATTERY_ICON,
            device_class=SensorDeviceClass.ENERGY,
            state_class=SensorStateClass.TOTAL,
            unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        )

    @property
    def native_value(self):
        """Return the state of the sensor."""
        processed_data = self._get_processed_data()
        return processed_data.get("total_battery_discharge")

class SajBatteryRoundTripEfficiencySensor(SajBaseSensor):
   """Sensor for SAJ battery round-trip efficiency."""

   def __init__(self, coordinator, device_sn, device_name):
       """Initialize the sensor."""
       super().__init__(
           coordinator=coordinator,
           device_sn=device_sn,
           device_name=device_name,
           name_suffix="Battery Efficiency",
           unique_id_suffix="battery_efficiency",
           icon=EFFICIENCY_ICON,
           state_class=SensorStateClass.MEASUREMENT,
           unit_of_measurement=PERCENTAGE,
       )

   @property
   def native_value(self):
       """Return the state of the sensor."""
       processed_data = self._get_processed_data()
       
       if "total_battery_charge" in processed_data and "total_battery_discharge" in processed_data:
           try:
               charge = float(processed_data["total_battery_charge"])
               discharge = float(processed_data["total_battery_discharge"])
               if charge > 0:
                   efficiency = (discharge / charge) * 100
                   return round(efficiency, 2)
           except (ValueError, TypeError, ZeroDivisionError):
               pass
           
       return None

class SajBackupLoadPowerSensor(SajBaseSensor):
   """Sensor for SAJ backup load power."""

   def __init__(self, coordinator, device_sn, device_name):
       """Initialize the sensor."""
       super().__init__(
           coordinator=coordinator,
           device_sn=device_sn,
           device_name=device_name,
           name_suffix="Backup Load Power",
           unique_id_suffix="backup_load_power",
           icon="mdi:power-plug",
           device_class=SensorDeviceClass.POWER,
           state_class=SensorStateClass.MEASUREMENT,
           unit_of_measurement=UnitOfPower.WATT,
       )

   @property
   def native_value(self):
       """Return the state of the sensor."""
       history_data = self._get_history_data()
       if "backupTotalLoadPowerWatt" in history_data:
           try:
               return float(history_data["backupTotalLoadPowerWatt"])
           except (ValueError, TypeError):
               pass
           
       return None

class SajTodayLoadEnergySensor(SajBaseSensor):
   """Sensor for SAJ today's load energy."""

   def __init__(self, coordinator, device_sn, device_name):
       """Initialize the sensor."""
       super().__init__(
           coordinator=coordinator,
           device_sn=device_sn,
           device_name=device_name,
           name_suffix="Today's Home Consumption",
           unique_id_suffix="today_load_energy",
           icon="mdi:home-lightning-bolt",
           device_class=SensorDeviceClass.ENERGY,
           state_class=SensorStateClass.TOTAL_INCREASING,
           unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
       )

   @property
   def native_value(self):
       """Return the state of the sensor."""
       processed_data = self._get_processed_data()
       return processed_data.get("today_load_energy")

class SajHomeLoadPowerSensor(SajBaseSensor):
   """Sensor for SAJ home load power."""

   def __init__(self, coordinator, device_sn, device_name):
       """Initialize the sensor."""
       super().__init__(
           coordinator=coordinator,
           device_sn=device_sn,
           device_name=device_name,
           name_suffix="Home Load Power",
           unique_id_suffix="home_load_power",
           icon="mdi:home-lightning-bolt",
           device_class=SensorDeviceClass.POWER,
           state_class=SensorStateClass.MEASUREMENT,
           unit_of_measurement=UnitOfPower.WATT,
       )

   @property
   def native_value(self):
       """Return the state of the sensor."""
       device_data = self._get_device_data()
       device_type = device_data.get("device_type")
       processed_data = self._get_processed_data()

       # For battery devices, try processed data which includes realtime data
       if device_type == DEVICE_TYPE_BATTERY and "home_load_power" in processed_data:
           return processed_data["home_load_power"]

       # For non-battery devices or if realtime data is not available
       # First try load monitoring data
       if "load_monitoring" in device_data and device_data["load_monitoring"]:
           latest = device_data["load_monitoring"].get("latest", {})
           if "loadPower" in latest:
               try:
                   return float(latest["loadPower"])
               except (ValueError, TypeError):
                   pass
       
       # Fall back to history data if available
       history_data = self._get_history_data()
       if "totalLoadPowerWatt" in history_data:
           try:
               return float(history_data["totalLoadPowerWatt"])
           except (ValueError, TypeError):
               pass
           
       return None

class SajCO2ReductionSensor(SajBaseSensor):
   """Sensor for SAJ CO2 reduction."""

   def __init__(self, coordinator, device_sn, device_name):
       """Initialize the sensor."""
       super().__init__(
           coordinator=coordinator,
           device_sn=device_sn,
           device_name=device_name,
           name_suffix="CO2 Reduction",
           unique_id_suffix="co2_reduction",
           icon=CO2_ICON,
           device_class=SensorDeviceClass.WEIGHT,
           state_class=SensorStateClass.TOTAL,
            unit_of_measurement="kg",
       )

   @property
   def native_value(self):
       """Return the state of the sensor."""
       plant_stats = self._get_plant_stats()
       if "totalReduceCo2" in plant_stats:
           try:
               tonnes = float(plant_stats["totalReduceCo2"])
               return tonnes * 1000  # Convert from tonnes to kg
           except (ValueError, TypeError):
               pass
           
       # Try processed data
       processed_data = self._get_processed_data()
       if "co2_reduction" in processed_data:
           return processed_data["co2_reduction"] * 1000  # Convert from tonnes to kg
           
       return None
   
   @property
   def extra_state_attributes(self):
         """Return the state attributes of the entity."""
         return {"original_unit": "tonnes"}
   
class SajEquivalentTreesSensor(SajBaseSensor):
   """Sensor for SAJ equivalent trees."""

   def __init__(self, coordinator, device_sn, device_name):
       """Initialize the sensor."""
       super().__init__(
           coordinator=coordinator,
           device_sn=device_sn,
           device_name=device_name,
           name_suffix="Equivalent Trees",
           unique_id_suffix="equivalent_trees",
           icon="mdi:tree",
           state_class=SensorStateClass.MEASUREMENT,
       )

   @property
   def native_value(self):
       """Return the state of the sensor."""
       plant_stats = self._get_plant_stats()
       if "totalPlantTreeNum" in plant_stats:
           try:
               return float(plant_stats["totalPlantTreeNum"])
           except (ValueError, TypeError):
               pass
           
       # Try processed data
       processed_data = self._get_processed_data()
       if "equivalent_trees" in processed_data:
           return processed_data["equivalent_trees"]
           
       return None

class SajEstimatedAnnualProductionSensor(SajBaseSensor):
   """Sensor for SAJ estimated annual production."""

   def __init__(self, coordinator, device_sn, device_name):
       """Initialize the sensor."""
       super().__init__(
           coordinator=coordinator,
           device_sn=device_sn,
           device_name=device_name,
           name_suffix="Estimated Annual Production",
           unique_id_suffix="estimated_annual_production",
           icon=ENERGY_ICON,
           device_class=SensorDeviceClass.ENERGY,
           unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
       )

   @property
   def native_value(self):
       """Return the state of the sensor."""
       processed_data = self._get_processed_data()
       if "estimated_annual_production" in processed_data:
           return round(processed_data["estimated_annual_production"], 2)
           
       return None

class SajEstimatedAnnualSavingsSensor(SajBaseSensor):
   """Sensor for SAJ estimated annual savings."""

   def __init__(self, coordinator, device_sn, device_name):
       """Initialize the sensor."""
       super().__init__(
           coordinator=coordinator,
           device_sn=device_sn,
           device_name=device_name,
           name_suffix="Estimated Annual Savings",
           unique_id_suffix="estimated_annual_savings",
           icon=MONEY_ICON,
       )

   @property
   def native_value(self):
       """Return the state of the sensor."""
       processed_data = self._get_processed_data()
       if "estimated_annual_savings" in processed_data:
           return round(processed_data["estimated_annual_savings"], 2)
           
       return None
       
   @property
   def extra_state_attributes(self):
       """Return the state attributes of the entity."""
       return {"unit": "$", "rate": "0.15 $/kWh"}


class SajTodayGridImportEnergySensor(SajBaseSensor):
   """Sensor for SAJ today's grid import energy."""

   def __init__(self, coordinator, device_sn, device_name):
       """Initialize the sensor."""
       super().__init__(
           coordinator=coordinator,
           device_sn=device_sn,
           device_name=device_name,
           name_suffix="Today's Grid Import Energy",
           unique_id_suffix="today_grid_import_energy",
           icon=GRID_ICON,
           device_class=SensorDeviceClass.ENERGY,
           state_class=SensorStateClass.TOTAL_INCREASING,
           unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
       )

   @property
   def native_value(self):
       """Return the state of the sensor."""
       processed_data = self._get_processed_data()
       return processed_data.get("today_grid_import_energy")

class SajTotalGridImportSensor(SajBaseSensor):
   """Sensor for SAJ total grid import energy."""

   def __init__(self, coordinator, device_sn, device_name):
       """Initialize the sensor."""
       super().__init__(
           coordinator=coordinator,
           device_sn=device_sn,
           device_name=device_name,
           name_suffix="Total Grid Import",
           unique_id_suffix="total_grid_import",
           icon=GRID_ICON,
           device_class=SensorDeviceClass.ENERGY,
           state_class=SensorStateClass.TOTAL,
           unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
       )

   @property
   def native_value(self):
       """Return the state of the sensor."""
       device_data = self._get_device_data()
       device_type = device_data.get("device_type")
       
       # For battery devices, try processed data which includes realtime data
       if device_type == DEVICE_TYPE_BATTERY:
           processed_data = self._get_processed_data()
           if "total_grid_import" in processed_data:
               return processed_data["total_grid_import"]
       
       return None

class SajTotalLoadEnergySensor(SajBaseSensor):
   """Sensor for SAJ total load energy."""

   def __init__(self, coordinator, device_sn, device_name):
       """Initialize the sensor."""
       super().__init__(
           coordinator=coordinator,
           device_sn=device_sn,
           device_name=device_name,
           name_suffix="Total Home Consumption",
           unique_id_suffix="total_load_energy",
           icon="mdi:home-lightning-bolt",
           device_class=SensorDeviceClass.ENERGY,
           state_class=SensorStateClass.TOTAL,
           unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
       )

   @property
   def native_value(self):
       """Return the state of the sensor."""
       device_data = self._get_device_data()
       device_type = device_data.get("device_type")
       
       # For battery devices, try processed data which includes realtime data
       if device_type == DEVICE_TYPE_BATTERY:
           processed_data = self._get_processed_data()
           if "total_load_energy" in processed_data:
               return processed_data["total_load_energy"]
       
       return None
