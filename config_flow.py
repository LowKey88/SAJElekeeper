"""Config flow for SAJ Solar & Battery Monitor integration."""
import logging
import voluptuous as vol
import async_timeout

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.const import CONF_NAME

from .const import (
    DOMAIN,
    CONF_APP_ID,
    CONF_APP_SECRET,
    CONF_DEVICES,
    CONF_DEVICE_NAME,
    CONF_DEVICE_SN,
    CONF_DEVICE_PLANT_ID,
    CONF_DEVICE_TYPE,
    DEVICE_TYPE_SOLAR,
    DEVICE_TYPE_BATTERY,
    BASE_URL,
    TOKEN_URL,
)

_LOGGER = logging.getLogger(__name__)

class SajConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for SAJ Solar & Battery Monitor."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    def __init__(self):
        """Initialize the config flow."""
        self.data = {}
        self.devices = []

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            # Validate credentials
            app_id = user_input[CONF_APP_ID]
            app_secret = user_input[CONF_APP_SECRET]
            
            valid = await self._test_credentials(app_id, app_secret)
            
            if valid:
                self.data = {
                    CONF_APP_ID: app_id,
                    CONF_APP_SECRET: app_secret,
                }
                # Proceed to adding devices
                return await self.async_step_add_device()
            else:
                errors["base"] = "auth_error"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_APP_ID): str,
                    vol.Required(CONF_APP_SECRET): str,
                }
            ),
            errors=errors,
        )

    async def async_step_add_device(self, user_input=None):
        """Handle adding a device."""
        errors = {}

        if user_input is not None:
            # Add device to the list
            device = {
                CONF_DEVICE_NAME: user_input[CONF_DEVICE_NAME],
                CONF_DEVICE_SN: user_input[CONF_DEVICE_SN],
                CONF_DEVICE_PLANT_ID: user_input[CONF_DEVICE_PLANT_ID],
                CONF_DEVICE_TYPE: user_input[CONF_DEVICE_TYPE],
            }
            
            # Convert to the format our code expects
            converted_device = {
                "name": device[CONF_DEVICE_NAME],
                "sn": device[CONF_DEVICE_SN],
                "plant_id": device[CONF_DEVICE_PLANT_ID],
                "type": device[CONF_DEVICE_TYPE],
            }
            
            self.devices.append(converted_device)
            
            # Ask if user wants to add another device
            return await self.async_step_add_another()

        return self.async_show_form(
            step_id="add_device",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_DEVICE_NAME): str,
                    vol.Required(CONF_DEVICE_SN): str,
                    vol.Required(CONF_DEVICE_PLANT_ID): str,
                    vol.Required(CONF_DEVICE_TYPE, default=DEVICE_TYPE_SOLAR): vol.In(
                        [DEVICE_TYPE_SOLAR, DEVICE_TYPE_BATTERY]
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_add_another(self, user_input=None):
        """Ask if user wants to add another device."""
        if user_input is not None:
            if user_input.get("add_another", False):
                return await self.async_step_add_device()
            else:
                # Finished adding devices, create the entry
                self.data[CONF_DEVICES] = self.devices
                return self.async_create_entry(
                    title=f"SAJ Monitor ({len(self.devices)} devices)",
                    data=self.data,
                )

        return self.async_show_form(
            step_id="add_another",
            data_schema=vol.Schema(
                {
                    vol.Required("add_another", default=False): bool,
                }
            ),
        )

    async def _test_credentials(self, app_id, app_secret):
        """Test if we can authenticate with the SAJ API."""
        try:
            session = async_get_clientsession(self.hass)
            token_url = f"{BASE_URL}{TOKEN_URL}"
            token_params = {"appId": app_id, "appSecret": app_secret}
            token_headers = {"content-language": "en_US"}

            async with async_timeout.timeout(10):
                token_resp = await session.get(token_url, params=token_params, headers=token_headers)
                token_json = await token_resp.json()

            if "data" not in token_json or "access_token" not in token_json["data"]:
                _LOGGER.error("Invalid token response: %s", token_json)
                return False

            return True
        except Exception as ex:
            _LOGGER.error("Error testing credentials: %s", ex)
            return False
