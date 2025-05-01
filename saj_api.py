"""SAJ API client for the SAJ Solar & Battery Monitor integration."""
import logging
import asyncio
import async_timeout
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import aiohttp
import hashlib
import hmac
import base64

from .const import (
    BASE_URL,
    TOKEN_URL,
    DEVICE_INFO_URL,
    PLANT_STATS_URL,
    HISTORY_DATA_URL,
    LOAD_MONITORING_URL,
    DEVICE_TYPE_SOLAR,
    DEVICE_TYPE_BATTERY,
)

_LOGGER = logging.getLogger(__name__)

class SajApiClient:
    """API client for SAJ Solar & Battery Monitor."""

    def __init__(self, app_id: str, app_secret: str, session: aiohttp.ClientSession):
        """Initialize the API client."""
        self._app_id = app_id
        self._app_secret = app_secret
        self._session = session
        self._token = None
        self._token_expires_at = datetime.now()
        
    def _generate_signature(self, token: str, params: Dict[str, str]) -> str:
        """Generate clientSign signature for API requests.
        
        Without specific documentation, this implements a common HMAC-SHA256 approach:
        1. Sort parameters alphabetically
        2. Create a string of key=value pairs
        3. Append the token and app_secret
        4. Generate HMAC-SHA256 using app_secret as key
        5. Return hex digest
        """
        # Sort parameters alphabetically
        sorted_params = sorted(params.items(), key=lambda x: x[0])
        
        # Create string of key=value pairs
        param_string = "&".join([f"{k}={v}" for k, v in sorted_params])
        
        # Append token
        message = f"{param_string}&accessToken={token}"
        
        # Generate HMAC-SHA256 using app_secret as key
        signature = hmac.new(
            self._app_secret.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()
        
        _LOGGER.debug("Generated signature for params: %s", params)
        return signature

    async def _get_token(self) -> str:
        """Get access token from SAJ API."""
        # Always fetch a new token for each request, like the working script does
        try:
            token_url = f"{BASE_URL}{TOKEN_URL}"
            token_params = {"appId": self._app_id, "appSecret": self._app_secret}
            token_headers = {"content-language": "en_US"}

            async with async_timeout.timeout(10):
                token_resp = await self._session.get(token_url, params=token_params, headers=token_headers)
                token_json = await token_resp.json()

            if "data" not in token_json or "access_token" not in token_json["data"]:
                _LOGGER.error("Invalid token response: %s", token_json)
                return None

            self._token = token_json["data"]["access_token"]
            # Token is valid for 2 hours, but we'll refresh it after 1 hour
            self._token_expires_at = datetime.now() + timedelta(hours=1)
            return self._token

        except asyncio.TimeoutError:
            _LOGGER.error("Timeout getting access token")
            return None
        except aiohttp.ClientError as ex:
            _LOGGER.error("HTTP error getting access token: %s", ex)
            return None
        except Exception as ex:
            _LOGGER.error("Error getting access token: %s", ex)
            return None

    async def get_device_details(self, device_sn: str) -> Optional[Dict[str, Any]]:
        """Get device details from SAJ API."""
        token = await self._get_token()
        if not token:
            return None

        try:
            device_url = f"{BASE_URL}{DEVICE_INFO_URL}"
            device_params = {"deviceSn": device_sn}
            # Match header case exactly with the working script
            device_headers = {
                "accessToken": token,  # Note: not "AccessToken" or "access-token"
                "content-language": "en_US",
            }

            async with async_timeout.timeout(10):
                device_resp = await self._session.get(device_url, params=device_params, headers=device_headers)
                device_json = await device_resp.json()

            if device_json.get("code") != 200 or "data" not in device_json:
                _LOGGER.error("Error in device details response: %s", device_json.get("msg", "Unknown error"))
                return None

            return device_json["data"]

        except asyncio.TimeoutError:
            _LOGGER.error("Timeout getting device details")
            return None
        except aiohttp.ClientError as ex:
            _LOGGER.error("HTTP error getting device details: %s", ex)
            return None
        except Exception as ex:
            _LOGGER.error("Error getting device details: %s", ex)
            return None

    async def get_plant_statistics(self, plant_id: str) -> Optional[Dict[str, Any]]:
        """Get plant statistics from SAJ API."""
        token = await self._get_token()
        if not token:
            return None

        try:
            now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            stats_url = f"{BASE_URL}{PLANT_STATS_URL}"
            stats_params = {"plantId": plant_id, "clientDate": now}
            # Match header case exactly with the working script
            stats_headers = {
                "accessToken": token,  # Note: not "AccessToken" or "access-token"
                "content-language": "en_US",
            }

            async with async_timeout.timeout(10):
                stats_resp = await self._session.get(stats_url, params=stats_params, headers=stats_headers)
                stats_json = await stats_resp.json()

            if "data" not in stats_json:
                _LOGGER.error("No data in plant statistics response")
                return None

            return stats_json["data"]

        except asyncio.TimeoutError:
            _LOGGER.error("Timeout getting plant statistics")
            return None
        except aiohttp.ClientError as ex:
            _LOGGER.error("HTTP error getting plant statistics: %s", ex)
            return None
        except Exception as ex:
            _LOGGER.error("Error getting plant statistics: %s", ex)
            return None

    async def get_history_data(self, device_sn: str) -> Optional[Dict[str, Any]]:
        """Get historical data from SAJ API."""
        token = await self._get_token()
        if not token:
            return None

        try:
            end_time = datetime.now()
            start_time = end_time - timedelta(hours=1)

            start_time_str = start_time.strftime("%Y-%m-%d %H:%M:%S")
            end_time_str = end_time.strftime("%Y-%m-%d %H:%M:%S")

            history_url = f"{BASE_URL}{HISTORY_DATA_URL}"
            history_params = {
                "deviceSn": device_sn,
                "startTime": start_time_str,
                "endTime": end_time_str
            }
            # Match header case exactly with the working script
            history_headers = {
                "accessToken": token,  # Note: not "AccessToken" or "access-token"
                "content-language": "en_US",
            }

            async with async_timeout.timeout(10):
                history_resp = await self._session.get(history_url, params=history_params, headers=history_headers)
                history_json = await history_resp.json()

            if history_json.get("code") != 200 or "data" not in history_json:
                _LOGGER.error("Error in history data response: %s", history_json.get("msg", "Unknown error"))
                return None

            history_data = history_json["data"]
            _LOGGER.debug("Raw history data received: %s", history_data) # Add debug logging

            if not isinstance(history_data, list) or not history_data:
                _LOGGER.error("No history data points found in response: %s", history_json)
                return None

            # Log the specific data point being returned
            most_recent_point = history_data[10]
            _LOGGER.debug("Using history data point: %s", most_recent_point)
            return most_recent_point # Return the most recent data point

        except asyncio.TimeoutError:
            _LOGGER.error("Timeout getting history data")
            return None
        except aiohttp.ClientError as ex:
            _LOGGER.error("HTTP error getting history data: %s", ex)
            return None
        except Exception as ex:
            _LOGGER.error("Error getting history data: %s", ex)
            return None

    async def get_load_monitoring_data(self, plant_id: str) -> Optional[Dict[str, Any]]:
        """Get load monitoring data from SAJ API."""
        token = await self._get_token()
        if not token:
            return None

        try:
            # Use current time for the request
            end_time = datetime.now()
            # Request data for the last hour
            start_time = end_time - timedelta(hours=1)
            
            start_time_str = start_time.strftime("%Y-%m-%d %H:%M:%S")
            end_time_str = end_time.strftime("%Y-%m-%d %H:%M:%S")
            
            url = f"{BASE_URL}{LOAD_MONITORING_URL}"
            params = {
                "plantId": plant_id,
                "startTime": start_time_str,
                "endTime": end_time_str,
                "timeUnit": 0  # 0 for minute-level data
            }
            
            headers = {
                "accessToken": token,
                "content-language": "en_US",
            }
            
            async with async_timeout.timeout(10):
                response = await self._session.get(url, params=params, headers=headers)
                data = await response.json()
            
            if data.get("code") != 200 or "data" not in data:
                _LOGGER.error("Error in load monitoring response: %s", data.get("msg", "Unknown error"))
                return None
                
            # Extract the most recent data point
            if "dataList" in data["data"] and data["data"]["dataList"]:
                for module in data["data"]["dataList"]:
                    if "data" in module and module["data"]:
                        # Get the most recent data point
                        latest_data = module["data"][-1]
                        # Also include the total values
                        return {
                            "latest": latest_data,
                            "total": module.get("total", {}),
                            "module_sn": module.get("moduleSn", "")
                        }
            
            return None
            
        except asyncio.TimeoutError:
            _LOGGER.error("Timeout getting load monitoring data")
            return None
        except aiohttp.ClientError as ex:
            _LOGGER.error("HTTP error getting load monitoring data: %s", ex)
            return None
        except Exception as ex:
            _LOGGER.error("Error getting load monitoring data: %s", ex)
            return None

    async def get_device_data(self, device: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Get all data for a device."""
        device_sn = device["sn"]
        plant_id = device["plant_id"]
        device_type = device["type"]

        # Get all types of data
        device_info = await self.get_device_details(device_sn)
        plant_stats = await self.get_plant_statistics(plant_id)
        history_data = await self.get_history_data(device_sn)
        load_monitoring = await self.get_load_monitoring_data(plant_id)

        # If any of them failed, log an error but continue with what we have
        if not device_info:
            _LOGGER.warning("Failed to get device details for %s", device_sn)
        if not plant_stats:
            _LOGGER.warning("Failed to get plant statistics for %s", plant_id)
        if not history_data:
            _LOGGER.warning("Failed to get history data for %s", device_sn)
            # History data is critical, return None if it's missing
            return None
        if not load_monitoring:
            _LOGGER.warning("Failed to get load monitoring data for %s", plant_id)
            # Load monitoring data is not critical, continue without it

        # Calculate actual PV power for R6 by summing inputs
        if device_type == DEVICE_TYPE_SOLAR:
            total_pv_power = 0
            for i in range(1, 4):  # Check first 3 inputs
                pv_power = float(history_data.get(f"pv{i}power", 0))
                total_pv_power += pv_power
            history_data["total_pv_power_calculated"] = total_pv_power
        else:
            # For AS1, use the reported value
            history_data["total_pv_power_calculated"] = float(history_data.get('totalPVPower', 0))

        # Fix grid status reporting
        grid_power = float(history_data.get('totalGridPowerWatt', 0))
        grid_direction = "exporting" if grid_power < 0 else "importing" if grid_power > 0 else "idle"
        history_data["grid_status_calculated"] = grid_direction
        history_data["grid_power_abs"] = abs(grid_power)

        # Fix battery status reporting (for battery devices)
        if device_type == DEVICE_TYPE_BATTERY:
            bat_power = float(history_data.get("batPower", 0))
            if bat_power > 0:
                bat_status = "discharging"
            elif bat_power < 0:
                bat_status = "charging"
            else:
                bat_status = "idle"
            history_data["battery_status_calculated"] = bat_status
            history_data["battery_power_abs"] = abs(bat_power)

        # Combine all data into a single dictionary
        return {
            "device_info": device_info,
            "plant_stats": plant_stats,
            "history_data": history_data,
            "load_monitoring": load_monitoring,
            "device_type": device_type,
        }
