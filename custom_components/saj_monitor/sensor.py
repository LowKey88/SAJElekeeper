"""Sensor platform for SAJ Solar & Battery Monitor integration."""
import logging
from typing import Dict, List, Any, Optional

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
)

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
        ])
        
        # Add grid-related entities
        entities.extend([
            SajGridPowerSensor(coordinator, device_sn, device_name),
            SajGridStatusSensor(coordinator, device_sn, device_name),
            SajTodayGridExportSensor(coordinator, device_sn, device_name),
        ])
        
        # Add load monitoring entities (for all device types)
        entities.extend([
            SajHomeLoadPowerSensor(coordinator, device_sn, device_name),
            SajSelfConsumptionPowerSensor(coordinator, device_sn, device_name),
        ])
        
        # Add solar-specific entities
        if device_type == DEVICE_TYPE_SOLAR:
            # Add PV input entities
            for i in range(1, 4):  # Check first 3 inputs
                entities.extend([
                    SajPVPowerSensor(coordinator, device_sn, device_name, i),
                    SajPVVoltageSensor(coordinator, device_sn, device_name, i),
                    SajPVCurrentSensor(coordinator, device_sn, device_name, i),
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
                SajLoadPowerSensor(coordinator, device_sn, device_name),
                SajTodayLoadEnergySensor(coordinator, device_sn, device_name),
            ])
    
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
        
        # Get device data
        device_data = self.coordinator.data.get(device_sn, {})
        device_info = device_data.get("device_info", {})
        
        # Set up device info
        if device_info and "deviceInfo" in device_info:
            inv_info = device_info["deviceInfo"]
            model = inv_info.get("invType", "Unknown")
            
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, device_sn)},
                name=device_name,
                manufacturer="SAJ",
                model=model,
                sw_version=inv_info.get("invMFW", "Unknown"),
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
        device_data = self._get_device_data()
        if not device_data or "plant_stats" not in device_data:
            return None
            
        return device_data["plant_stats"].get("plantName")

class SajCurrentPowerSensor(SajBaseSensor):
    """Sensor for SAJ current power."""

    def __init__(self, coordinator, device_sn, device_name):
        """Initialize the sensor."""
        super().__init__(
            coordinator=coordinator,
            device_sn=device_sn,
            device_name=device_name,
            name_suffix="Current Power",
            unique_id_suffix="current_power",
            icon=POWER_ICON,
            device_class=SensorDeviceClass.POWER,
            state_class=SensorStateClass.MEASUREMENT,
            unit_of_measurement=UnitOfPower.WATT,
        )

    @property
    def native_value(self):
        """Return the state of the sensor."""
        device_data = self._get_device_data()
        if not device_data:
            return None
            
        # First try plant statistics (more accurate)
        if "plant_stats" in device_data:
            power_now = device_data["plant_stats"].get("powerNow")
            if power_now is not None:
                return power_now
            
        # Fall back to calculated value from history data
        if "history_data" in device_data:
            return device_data["history_data"].get("total_pv_power_calculated")
            
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
        if not device_data:
            return None
            
        # First try history data
        if "history_data" in device_data:
            today_energy = device_data["history_data"].get("todayPvEnergy")
            if today_energy is not None:
                return float(today_energy)
            
        # Fall back to plant statistics
        if "plant_stats" in device_data:
            return device_data["plant_stats"].get("todayPvEnergy")
            
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
        if not device_data or "plant_stats" not in device_data:
            return None
            
        return device_data["plant_stats"].get("totalPvEnergy")

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
        
        self._mode_descriptions = {
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
        if not device_data or "history_data" not in device_data:
            return None
            
        mpv_mode = device_data["history_data"].get("mpvMode")
        if mpv_mode is None:
            return None
            
        mpv_mode = int(mpv_mode)
        return self._mode_descriptions.get(mpv_mode, f"Unknown mode ({mpv_mode})")

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
        if not device_data:
            return None
            
        # First try load monitoring data
        if "load_monitoring" in device_data and device_data["load_monitoring"]:
            latest = device_data["load_monitoring"].get("latest", {})
            buy_power = latest.get("buyPower", 0)
            sell_power = latest.get("sellPower", 0)
            
            # If buying power, return that value
            if buy_power > 0:
                return float(buy_power)
            # If selling power, return that value (as positive)
            elif sell_power > 0:
                return float(sell_power)
            # If neither, return 0
            return 0
        
        # Fall back to history data
        if "history_data" in device_data:
            return device_data["history_data"].get("grid_power_abs")
            
        return None
        
    @property
    def extra_state_attributes(self):
        """Return the state attributes of the entity."""
        device_data = self._get_device_data()
        if not device_data:
            return {}
            
        # First try load monitoring data
        if "load_monitoring" in device_data and device_data["load_monitoring"]:
            latest = device_data["load_monitoring"].get("latest", {})
            buy_power = latest.get("buyPower", 0)
            sell_power = latest.get("sellPower", 0)
            
            if buy_power > 0:
                return {"status": "importing"}
            elif sell_power > 0:
                return {"status": "exporting"}
            else:
                return {"status": "idle"}
        
        # Fall back to history data
        if "history_data" in device_data:
            grid_status = device_data["history_data"].get("grid_status_calculated")
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
        device_data = self._get_device_data()
        if not device_data:
            return None
            
        # First try load monitoring data
        if "load_monitoring" in device_data and device_data["load_monitoring"]:
            latest = device_data["load_monitoring"].get("latest", {})
            buy_power = latest.get("buyPower", 0)
            sell_power = latest.get("sellPower", 0)
            
            if buy_power > 0:
                return "importing"
            elif sell_power > 0:
                return "exporting"
            else:
                return "idle"
        
        # Fall back to history data
        if "history_data" in device_data:
            return device_data["history_data"].get("grid_status_calculated")
            
        return None

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
        if not device_data:
            return None
            
        # First try history data
        if "history_data" in device_data:
            today_export = device_data["history_data"].get("todaySellEnergy")
            if today_export is not None:
                return float(today_export)
            
        # Fall back to plant statistics
        if "plant_stats" in device_data:
            return device_data["plant_stats"].get("todaySellEnergy")
            
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
        device_data = self._get_device_data()
        if not device_data or "history_data" not in device_data:
            return None
            
        power_key = f"pv{self._pv_input}power"
        power_value = device_data["history_data"].get(power_key)
        if power_value is None:
            return None
            
        return float(power_value)
        
    @property
    def available(self):
        """Return if entity is available."""
        if not super().available:
            return False
            
        device_data = self._get_device_data()
        if not device_data or "history_data" not in device_data:
            return False
            
        # Only consider available if the PV input has actual power
        power_key = f"pv{self._pv_input}power"
        power_value = device_data["history_data"].get(power_key)
        if power_value is None or float(power_value) <= 0:
            return False
            
        return True

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
        device_data = self._get_device_data()
        if not device_data or "history_data" not in device_data:
            return None
            
        voltage_key = f"pv{self._pv_input}volt"
        voltage_value = device_data["history_data"].get(voltage_key)
        if voltage_value is None:
            return None
            
        return float(voltage_value)
        
    @property
    def available(self):
        """Return if entity is available."""
        if not super().available:
            return False
            
        device_data = self._get_device_data()
        if not device_data or "history_data" not in device_data:
            return False
            
        # Only consider available if the PV input has actual power
        power_key = f"pv{self._pv_input}power"
        power_value = device_data["history_data"].get(power_key)
        if power_value is None or float(power_value) <= 0:
            return False
            
        return True

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
        device_data = self._get_device_data()
        if not device_data or "history_data" not in device_data:
            return None
            
        current_key = f"pv{self._pv_input}curr"
        current_value = device_data["history_data"].get(current_key)
        if current_value is None:
            return None
            
        return float(current_value)
        
    @property
    def available(self):
        """Return if entity is available."""
        if not super().available:
            return False
            
        device_data = self._get_device_data()
        if not device_data or "history_data" not in device_data:
            return False
            
        # Only consider available if the PV input has actual power
        power_key = f"pv{self._pv_input}power"
        power_value = device_data["history_data"].get(power_key)
        if power_value is None or float(power_value) <= 0:
            return False
            
        return True

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
        device_data = self._get_device_data()
        if not device_data or "history_data" not in device_data:
            return None
            
        bat_percent = device_data["history_data"].get("batEnergyPercent")
        if bat_percent is None:
            return None
            
        return float(bat_percent)

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
        device_data = self._get_device_data()
        if not device_data or "history_data" not in device_data:
            return None
            
        # Return the absolute value
        return device_data["history_data"].get("battery_power_abs")
        
    @property
    def extra_state_attributes(self):
        """Return the state attributes of the entity."""
        device_data = self._get_device_data()
        if not device_data or "history_data" not in device_data:
            return {}
            
        battery_status = device_data["history_data"].get("battery_status_calculated")
        return {"status": battery_status}

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
        device_data = self._get_device_data()
        if not device_data or "history_data" not in device_data:
            return None
            
        return device_data["history_data"].get("battery_status_calculated")

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
        device_data = self._get_device_data()
        if not device_data or "history_data" not in device_data:
            return None
            
        bat_temp = device_data["history_data"].get("batTempC")
        if bat_temp is None:
            return None
            
        return float(bat_temp)

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
        device_data = self._get_device_data()
        if not device_data or "history_data" not in device_data:
            return None
            
        charge = device_data["history_data"].get("todayBatChgEnergy")
        if charge is None:
            return None
            
        return float(charge)

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
        device_data = self._get_device_data()
        if not device_data or "history_data" not in device_data:
            return None
            
        discharge = device_data["history_data"].get("todayBatDisEnergy")
        if discharge is None:
            return None
            
        return float(discharge)

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
        if not device_data:
            return None
            
        # First try load monitoring data
        if "load_monitoring" in device_data and device_data["load_monitoring"]:
            latest = device_data["load_monitoring"].get("latest", {})
            return latest.get("loadPower")
        
        # Fall back to history data if available
        if "history_data" in device_data:
            return device_data["history_data"].get("totalLoadPowerWatt")
            
        return None

class SajSelfConsumptionPowerSensor(SajBaseSensor):
    """Sensor for SAJ self-consumption power."""

    def __init__(self, coordinator, device_sn, device_name):
        """Initialize the sensor."""
        super().__init__(
            coordinator=coordinator,
            device_sn=device_sn,
            device_name=device_name,
            name_suffix="Self-Consumption Power",
            unique_id_suffix="self_consumption_power",
            icon=SOLAR_ICON,
            device_class=SensorDeviceClass.POWER,
            state_class=SensorStateClass.MEASUREMENT,
            unit_of_measurement=UnitOfPower.WATT,
        )

    @property
    def native_value(self):
        """Return the state of the sensor."""
        device_data = self._get_device_data()
        if not device_data or "load_monitoring" not in device_data:
            return None
            
        latest = device_data["load_monitoring"].get("latest", {})
        return latest.get("selfUsePower")

class SajLoadPowerSensor(SajBaseSensor):
    """Sensor for SAJ load power."""

    def __init__(self, coordinator, device_sn, device_name):
        """Initialize the sensor."""
        super().__init__(
            coordinator=coordinator,
            device_sn=device_sn,
            device_name=device_name,
            name_suffix="Load Power",
            unique_id_suffix="load_power",
            icon="mdi:home-lightning-bolt",
            device_class=SensorDeviceClass.POWER,
            state_class=SensorStateClass.MEASUREMENT,
            unit_of_measurement=UnitOfPower.WATT,
        )

    @property
    def native_value(self):
        """Return the state of the sensor."""
        device_data = self._get_device_data()
        if not device_data or "history_data" not in device_data:
            return None
            
        load_power = device_data["history_data"].get("totalLoadPowerWatt")
        if load_power is None:
            return None
            
        return float(load_power)

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
        device_data = self._get_device_data()
        if not device_data or "history_data" not in device_data:
            return None
            
        load_energy = device_data["history_data"].get("todayLoadEnergy")
        if load_energy is None:
            return None
            
        return float(load_energy)
