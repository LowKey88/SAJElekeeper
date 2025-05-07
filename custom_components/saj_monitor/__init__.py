"""The SAJ Solar & Battery Monitor integration."""
import asyncio
import logging
from datetime import timedelta

import async_timeout
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    DOMAIN,
    CONF_APP_ID,
    CONF_APP_SECRET,
    CONF_DEVICES,
    DEFAULT_SCAN_INTERVAL,
    ERROR_AUTH,
    ERROR_COMM,
    ERROR_UNKNOWN,
)
from .saj_api import SajApiClient

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "binary_sensor"]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SAJ Monitor from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    
    # Get configuration
    app_id = entry.data[CONF_APP_ID]
    app_secret = entry.data[CONF_APP_SECRET]
    devices = entry.data[CONF_DEVICES]
    
    # Create API client
    session = async_get_clientsession(hass)
    api_client = SajApiClient(app_id, app_secret, session)
    
    # Create update coordinator
    coordinator = SajDataUpdateCoordinator(
        hass,
        _LOGGER,
        api_client=api_client,
        devices=devices,
        name=DOMAIN,
        update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
    )
    
    # Fetch initial data
    await coordinator.async_refresh()
    
    # Store coordinator
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "api_client": api_client,
        "session": session,
    }
    
    # Set up all platforms - use the recommended method
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    # Register unload handlers
    entry.async_on_unload(entry.add_update_listener(update_listener))
    
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    # Clean up resources
    if unload_ok and entry.entry_id in hass.data[DOMAIN]:
        # No need to close the session as it's managed by Home Assistant
        del hass.data[DOMAIN][entry.entry_id]
    
    return unload_ok

async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)

class SajDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching SAJ data."""

    def __init__(
        self,
        hass: HomeAssistant,
        logger: logging.Logger,
        api_client: SajApiClient,
        devices: list,
        name: str,
        update_interval: timedelta,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            logger,
            name=name,
            update_interval=update_interval,
        )
        self.api_client = api_client
        self.devices = devices

    async def _async_update_data(self):
        """Fetch data from API."""
        try:
            async with async_timeout.timeout(30):
                # Fetch data for all devices
                data = {}
                
                for device in self.devices:
                    device_data = await self.api_client.get_device_data(device)
                    if device_data:
                        # Use device SN as key
                        data[device["sn"]] = device_data
                    else:
                        self.logger.error("Failed to get data for device %s", device["sn"])
                
                if not data:
                    raise UpdateFailed("Failed to get data for any device")
                
                return data
                
        except asyncio.TimeoutError as ex:
            raise UpdateFailed(f"Timeout communicating with API: {ex}") from ex
        except Exception as ex:
            raise UpdateFailed(f"Error communicating with API: {ex}") from ex
