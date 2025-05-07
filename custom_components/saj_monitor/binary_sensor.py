"""Binary sensor platform for SAJ Solar & Battery Monitor integration."""
import logging
from typing import Dict, Any, Optional

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorDeviceClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.const import STATE_ON, STATE_OFF

from .const import (
    DOMAIN,
    CONF_DEVICES,
    DEVICE_TYPE_SOLAR,
    DEVICE_TYPE_BATTERY,
    ONLINE_ICON,
    OFFLINE_ICON,
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up SAJ binary sensors based on a config entry."""
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
            
        # Add online status binary sensor (for both solar and battery devices)
        # Focus on solar devices first but support both
        entities.append(SajDeviceOnlineStatusBinarySensor(coordinator, device_sn, device_name))
    
    async_add_entities(entities)

class SajBaseBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Base class for SAJ binary sensors."""

    def __init__(self, coordinator, device_sn, device_name, name_suffix, unique_id_suffix,
                icon=None, device_class=None, entity_category=None):
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        
        self._device_sn = device_sn
        self._device_name = device_name
        self._attr_name = f"{device_name} {name_suffix}"
        self._attr_unique_id = f"{device_sn}_{unique_id_suffix}"
        self._attr_icon = icon
        self._attr_device_class = device_class
        self._attr_entity_category = entity_category
        
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
                history_data = device_data.get("history_data") or {}
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
        history_data = device_data.get("history_data") or {}
        return history_data if isinstance(history_data, dict) else {}
    
    def _get_realtime_data(self):
        """Get realtime data from coordinator."""
        device_data = self._get_device_data()
        if not device_data:
            return {}
        realtime_data = device_data.get("realtime_data")
        return realtime_data if isinstance(realtime_data, dict) else {}
    
    def _get_processed_data(self):
        """Get processed data from coordinator."""
        device_data = self._get_device_data()
        if not device_data:
            return {}
        processed_data = device_data.get("processed_data") or {}
        return processed_data if isinstance(processed_data, dict) else {}

class SajDeviceOnlineStatusBinarySensor(SajBaseBinarySensor):
    """Binary sensor for SAJ solar inverter online status."""

    def __init__(self, coordinator, device_sn, device_name):
        """Initialize the binary sensor."""
        super().__init__(
            coordinator=coordinator,
            device_sn=device_sn,
            device_name=device_name,
            name_suffix="Connection Status",
            unique_id_suffix="connection_status",
            icon=ONLINE_ICON,
            device_class=BinarySensorDeviceClass.CONNECTIVITY,
            entity_category=EntityCategory.DIAGNOSTIC,
        )
    
    def _is_nighttime(self):
        """Determine if it's likely nighttime based on available data."""
        device_data = self._get_device_data()
        
        # Check if we have any history or realtime data
        has_history = bool(device_data.get("history_data"))
        has_realtime = bool(self._get_realtime_data())
        
        # Check if we have load monitoring data (which works 24/7)
        has_load_monitoring = bool(device_data.get("load_monitoring"))
        
        # Check processed data for PV power
        processed_data = self._get_processed_data()
        pv_power = processed_data.get("total_pv_power_calculated", 0)
        
        # It's likely nighttime if:
        # 1. We have load monitoring data (API is working)
        # 2. But no history data or very low/zero PV power
        # 3. And realtime data doesn't show online status
        return (has_load_monitoring and 
                (not has_history or pv_power < 5) and 
                not (has_realtime and self._get_realtime_data().get("isOnline") == "1"))

    @property
    def is_on(self) -> bool:
        """Return true if the device is online."""
        # Get realtime data which contains the isOnline field
        realtime_data = self._get_realtime_data()
        device_data = self._get_device_data()
        device_type = device_data.get("device_type")
        
        # Log key information for debugging
        _LOGGER.debug(
            "Connection status for device %s (type: %s): has_realtime_data=%s, isOnline=%s", 
            self._device_sn, 
            device_type,
            bool(realtime_data),
            realtime_data.get("isOnline") if realtime_data else "N/A"
        )
        
        # If we have realtime data and it shows online, device is online
        if realtime_data and realtime_data.get("isOnline") == "1":
            return True
            
        # Special handling for battery systems - they should generally be online
        # Battery devices are usually always online (even at night), so we need different logic
        if device_type == DEVICE_TYPE_BATTERY:
            # For battery systems, check if we have any realtime data at all
            # Even if isOnline is not "1", having any realtime data suggests it's connected
            if realtime_data:
                # Additional check for battery devices - if we have processed data with battery level,
                # consider it online even if isOnline flag is not set to "1"
                processed_data = self._get_processed_data()
                if processed_data and "battery_level" in processed_data:
                    _LOGGER.debug("Battery device has battery_level data, considering it online")
                    return True
        
        # For solar devices, if it's nighttime, we treat the status differently
        if device_type == DEVICE_TYPE_SOLAR and self._is_nighttime():
            # During nighttime, still return False (disconnected) but we'll add context in attributes
            _LOGGER.debug("Solar device in nighttime mode, showing as offline with context")
            return False
        
        # Otherwise, genuinely disconnected
        return False
    
    @property
    def icon(self):
        """Return the icon based on the device's status."""
        return ONLINE_ICON if self.is_on else OFFLINE_ICON
        
    @property
    def extra_state_attributes(self):
        """Return additional attributes about the device's status."""
        realtime_data = self._get_realtime_data()
        
        # Return raw isOnline value and the last time data was fetched
        attributes = {}
        
        # Add raw status info from realtime data if available
        if realtime_data:
            attributes["raw_online_status"] = realtime_data.get("isOnline", "unknown")
            
            # Add last update time if available
            if "recordTime" in realtime_data:
                attributes["last_update_time"] = realtime_data["recordTime"]
        
        # Add specific status notes based on device type
        device_data = self._get_device_data()
        device_type = device_data.get("device_type")
        
        if device_type == DEVICE_TYPE_SOLAR and self._is_nighttime():
            # For solar devices at night
            attributes["is_nighttime"] = True
            attributes["status_note"] = "Solar inverter is in sleep mode (normal during nighttime)"
        elif device_type == DEVICE_TYPE_BATTERY and not self.is_on:
            # For offline battery systems
            attributes["status_note"] = "Battery system appears to be disconnected"
            # Add some diagnostic info for battery systems
            if realtime_data:
                attributes["battery_data_available"] = "Has some data but not showing as connected"
        
        # Add data availability info to help with debugging
        attributes["has_realtime_data"] = bool(realtime_data)
        attributes["has_history_data"] = bool(device_data.get("history_data"))
        attributes["has_load_monitoring"] = bool(device_data.get("load_monitoring"))
        
        # Include PV power if available
        processed_data = self._get_processed_data()
        if "total_pv_power_calculated" in processed_data:
            attributes["pv_power"] = processed_data["total_pv_power_calculated"]
        
        return attributes