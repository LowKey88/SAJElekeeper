"""Binary sensor platform for SAJ Solar & Battery Monitor integration."""
import logging
from typing import Dict, Any, Optional

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
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
            
        # Add status binary sensor
        entities.append(SajDeviceStatusBinarySensor(coordinator, device_sn, device_name))
    
    # Simple info log
    _LOGGER.info("Set up %d SAJ inverter status sensors", len(entities))
    async_add_entities(entities)

class SajBaseBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Base class for SAJ binary sensors."""

    def __init__(self, coordinator, device_sn, device_name, name_suffix, unique_id_suffix,
                icon=None, entity_category=None):
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        
        self._device_sn = device_sn
        self._device_name = device_name
        self._attr_name = f"{device_name} {name_suffix}"
        self._attr_unique_id = f"{device_sn}_{unique_id_suffix}"
        self._attr_icon = icon
        self._attr_device_class = None
        self._attr_entity_category = entity_category
        # Cache for the current state to avoid recalculating repeatedly
        self._current_state = None
        
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
        
        # Simple debug logging - only on entity creation
        _LOGGER.debug("Initialized status sensor for %s", self._device_name)

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

class SajDeviceStatusBinarySensor(SajBaseBinarySensor):
    """Binary sensor for SAJ device status."""

    def __init__(self, coordinator, device_sn, device_name):
        """Initialize the binary sensor."""
        # Determine the right name suffix and unique_id_suffix based on device type
        device_data = coordinator.data.get(device_sn, {})
        device_type = device_data.get("device_type", "")
        
        if device_type == DEVICE_TYPE_BATTERY:
            name_suffix = "Battery Inverter Status"
            unique_id_suffix = "battery_inverter_status"
        elif device_type == DEVICE_TYPE_SOLAR:
            name_suffix = "Solar Inverter Status"
            unique_id_suffix = "solar_inverter_status"
        else:
            # Generic fallback
            name_suffix = "Inverter Status"
            unique_id_suffix = "inverter_status"
        
        # Use the new unique ID but no device class
        super().__init__(
            coordinator=coordinator,
            device_sn=device_sn,
            device_name=device_name,
            name_suffix=name_suffix,
            unique_id_suffix=unique_id_suffix,
            icon=ONLINE_ICON,
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
                
    def _determine_state(self):
        """Determine the current state without logging."""
        realtime_data = self._get_realtime_data()
        device_data = self._get_device_data()
        device_type = device_data.get("device_type")
        
        # Check if online based on realtime data
        if realtime_data and realtime_data.get("isOnline") == "1":
            return True
        
        # Check if it's a solar device at night
        if device_type == DEVICE_TYPE_SOLAR and self._is_nighttime():
            return False
        
        # Otherwise, device is offline
        return False
    
    def _update_if_needed(self):
        """Update state if coordinator has been updated."""
        if self.coordinator.last_update_success:
            new_state = self._determine_state()
            
            # Only log if state has changed or this is the first check
            if self._current_state is None or self._current_state != new_state:
                device_data = self._get_device_data()
                device_type = device_data.get("device_type")
                
                if device_type == DEVICE_TYPE_SOLAR and self._is_nighttime():
                    _LOGGER.debug("%s status: Offline (nighttime)", self._device_name)
                else:
                    _LOGGER.debug("%s status: %s", self._device_name, "Online" if new_state else "Offline")
                
                # Update our cached state
                self._current_state = new_state
                
            return new_state
        return self._current_state if self._current_state is not None else False

    @property
    def is_on(self) -> bool:
        """Return true if the device is online."""
        return self._update_if_needed()
    
    @property
    def state(self) -> str:
        """Return the state of the binary sensor.
        
        This method overrides the default to return Online/Offline instead of on/off.
        """
        if self.is_on:
            return "Online"
        return "Offline"
    
    @property
    def icon(self):
        """Return the icon based on the device's status."""
        return ONLINE_ICON if self.is_on else OFFLINE_ICON
        
    @property
    def device_state_attributes(self):
        """Return the state attributes of the entity (for Home Assistant < 2022.07)."""
        return self.extra_state_attributes
        
    @property
    def extra_state_attributes(self):
        """Return additional attributes about the device's status."""
        realtime_data = self._get_realtime_data()
        device_data = self._get_device_data()
        device_type = device_data.get("device_type")
        
        attributes = {}
        
        # Add simplified status
        attributes["status"] = "Online" if self.is_on else "Offline"
        
        # For solar devices at night, add minimal context
        if device_type == DEVICE_TYPE_SOLAR and self._is_nighttime():
            attributes["is_nighttime"] = True
            attributes["note"] = "Normal during nighttime"
        
        # Add last update time if available
        if realtime_data and "recordTime" in realtime_data:
            attributes["last_update"] = realtime_data["recordTime"]
            
        return attributes