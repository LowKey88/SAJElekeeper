"""SAJ API client for the SAJ Solar & Battery Monitor integration."""
import logging
import asyncio
import async_timeout
from datetime import timedelta
from typing import Dict, List, Any, Optional, Tuple
import aiohttp
import hashlib
import hmac
import base64
import json
from homeassistant.util import dt as dt_util

from .const import (
    BASE_URL,
    TOKEN_URL,
    DEVICE_INFO_URL,
    PLANT_STATS_URL,
    HISTORY_DATA_URL,
    LOAD_MONITORING_URL,
    REALTIME_DATA_URL,
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
        self._token_expires_at = dt_util.now()
        
    async def _get_token(self) -> str:
        """Get access token from SAJ API."""
        # Always fetch a new token for each request, like the working script does
        try:
            token_url = f"{BASE_URL}{TOKEN_URL}"
            token_params = {"appId": self._app_id, "appSecret": self._app_secret}
            token_headers = {"content-language": "en_US"}

            _LOGGER.debug("Requesting auth token from %s", token_url)
            
            async with async_timeout.timeout(10):
                token_resp = await self._session.get(token_url, params=token_params, headers=token_headers)
                token_json = await token_resp.json()

            if "data" not in token_json or "access_token" not in token_json["data"]:
                _LOGGER.error("Invalid token response: %s", token_json)
                return None

            self._token = token_json["data"]["access_token"]
            # Token is valid for 2 hours, but we'll refresh it after 1 hour
            self._token_expires_at = dt_util.now() + timedelta(hours=1)
            _LOGGER.debug("Successfully obtained auth token")
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

    async def _make_api_request(self, endpoint: str, params: Dict, headers: Dict = None) -> Optional[Dict]:
        """Make an API request with error handling."""
        token = await self._get_token()
        if not token:
            _LOGGER.error("Failed to get auth token for API request to %s", endpoint)
            return None

        url = f"{BASE_URL}{endpoint}"
        
        # Set up default headers
        if headers is None:
            headers = {}
        
        # Always include these headers
        headers.update({
            "accessToken": token,
            "content-language": "en_US",
        })

        try:
            _LOGGER.debug("API request to %s with params: %s", url, params)
            
            async with async_timeout.timeout(10):
                response = await self._session.get(url, params=params, headers=headers)
                data = await response.json()

            if data.get("code") != 200 or "data" not in data:
                _LOGGER.error("Error in API response from %s: %s", endpoint, data.get("msg", "Unknown error"))
                return None

            _LOGGER.debug("Successful API response from %s", endpoint)
            return data["data"]

        except asyncio.TimeoutError:
            _LOGGER.error("Timeout during API request to %s", endpoint)
            return None
        except aiohttp.ClientError as ex:
            _LOGGER.error("HTTP error during API request to %s: %s", endpoint, ex)
            return None
        except Exception as ex:
            _LOGGER.error("Unexpected error during API request to %s: %s", endpoint, ex)
            return None

    async def get_device_details(self, device_sn: str) -> Optional[Dict[str, Any]]:
        """Get device details from SAJ API."""
        _LOGGER.debug("Fetching device details for device %s", device_sn)
        params = {"deviceSn": device_sn}
        return await self._make_api_request(DEVICE_INFO_URL, params)

    async def get_plant_statistics(self, plant_id: str) -> Optional[Dict[str, Any]]:
        """Get plant statistics from SAJ API."""
        _LOGGER.debug("Fetching plant statistics for plant %s", plant_id)
        now = dt_util.now().strftime("%Y-%m-%d %H:%M:%S")
        params = {"plantId": plant_id, "clientDate": now}
        headers = {"Content-Type": "application/json"}
        return await self._make_api_request(PLANT_STATS_URL, params, headers)

    async def get_history_data(self, device_sn: str, plant_id: str) -> Optional[Dict[str, Any]]:
        """Get historical data from SAJ API."""
        end_time = dt_util.now()
        start_time = end_time - timedelta(minutes=10)  # Use last 10 minutes for more recent data

        start_time_str = start_time.strftime("%Y-%m-%d %H:%M:%S")
        end_time_str = end_time.strftime("%Y-%m-%d %H:%M:%S")

        _LOGGER.debug(
            "Fetching history data for device %s (plant %s) from %s to %s",
            device_sn, plant_id, start_time_str, end_time_str
        )

        params = {
            "deviceSn": device_sn,
            "plantId": plant_id,  # Include plantId for better reliability
            "startTime": start_time_str,
            "endTime": end_time_str
        }
        
        try:
            token = await self._get_token()
            if not token:
                return None

            history_url = f"{BASE_URL}{HISTORY_DATA_URL}"
            history_headers = {
                "accessToken": token,
                "content-language": "en_US",
            }

            async with async_timeout.timeout(10):
                history_resp = await self._session.get(history_url, params=params, headers=history_headers)
                history_json = await history_resp.json()

            if history_json.get("code") != 200:
                _LOGGER.error("Error in history data response: %s", history_json.get("msg", "Unknown error"))
                return None
                
            if "data" not in history_json:
                # Special case: sometimes the API returns "request success" in the msg field
                # but doesn't include any data - this is normal during nighttime
                if history_json.get("msg") == "request success":
                    _LOGGER.debug("History data API returned 'request success' but no data - likely nighttime")
                    return {}
                else:
                    _LOGGER.error("No data in history data response: %s", history_json.get("msg", "Unknown error"))
                    return None

            history_data = history_json["data"]
            
            if not isinstance(history_data, list) or not history_data:
                _LOGGER.error("No history data points found in response")
                return None

            # Return the most recent data point (first in the list)
            _LOGGER.debug("Successfully retrieved history data for device %s (point count: %d)", 
                        device_sn, len(history_data))
            return history_data[0]

        except asyncio.TimeoutError:
            _LOGGER.error("Timeout getting history data for device %s", device_sn)
            return None
        except aiohttp.ClientError as ex:
            _LOGGER.error("HTTP error getting history data for device %s: %s", device_sn, ex)
            return None
        except Exception as ex:
            _LOGGER.error("Error getting history data for device %s: %s", device_sn, ex)
            return None

    async def get_realtime_data(self, device_sn: str) -> Optional[Dict[str, Any]]:
        """Get realtime data from SAJ API."""
        _LOGGER.debug("Fetching realtime data for device %s", device_sn)
        params = {"deviceSn": device_sn}
        result = await self._make_api_request(REALTIME_DATA_URL, params)
        
        if result:
            is_online = result.get("isOnline", "0")
            _LOGGER.debug("Device %s online status: %s", device_sn, "Online" if is_online == "1" else "Offline")
        
        return result

    async def get_load_monitoring_data(self, plant_id: str) -> Optional[Dict[str, Any]]:
        """Get load monitoring data from SAJ API."""
        # Get the current time
        now = dt_util.now()
        
        # Start time is midnight of the current day
        today_midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Use current time as end time to get all data for today so far
        start_time_str = today_midnight.strftime("%Y-%m-%d %H:%M:%S")
        end_time_str = now.strftime("%Y-%m-%d %H:%M:%S")
        
        _LOGGER.debug(
            "Fetching load monitoring data for plant %s from %s to %s",
            plant_id, start_time_str, end_time_str
        )
        
        params = {
            "plantId": plant_id,
            "startTime": start_time_str,
            "endTime": end_time_str,
            "timeUnit": 0  # 0 for minute-level data
        }
        
        try:
            token = await self._get_token()
            if not token:
                return None

            url = f"{BASE_URL}{LOAD_MONITORING_URL}"
            headers = {
                "accessToken": token,
                "content-language": "en_US",
            }
            
            async with async_timeout.timeout(10):
                response = await self._session.get(url, params=params, headers=headers)
                data = await response.json()
            
            if data.get("code") != 200 or "data" not in data:
                # Some systems don't have load monitoring
                if "plant has not been bound with load monitoring" in data.get("msg", ""):
                    _LOGGER.info("Plant %s does not have load monitoring", plant_id)
                else:
                    _LOGGER.error("Error in load monitoring response: %s", data.get("msg", "Unknown error"))
                return None
                
            # Extract the most recent data point
            if "dataList" in data["data"] and data["data"]["dataList"]:
                for module in data["data"]["dataList"]:
                    if "data" in module and module["data"]:
                        # Get the most recent data point
                        latest_data = module["data"][-1]
                        result = {
                            "latest": latest_data,
                            "total": module.get("total", {}),
                            "module_sn": module.get("moduleSn", "")
                        }
                        
                        _LOGGER.debug("Successfully retrieved load monitoring data for plant %s, module %s", 
                                    plant_id, result.get("module_sn", "unknown"))
                        
                        # Log key metrics
                        latest = result.get("latest", {})
                        total = result.get("total", {})
                        _LOGGER.debug("Latest metrics - Load: %sW, Buy: %sW, Sell: %sW", 
                                    latest.get("loadPower", "N/A"), 
                                    latest.get("buyPower", "N/A"),
                                    latest.get("sellPower", "N/A"))
                        _LOGGER.debug("Today totals - Load: %skWh, Buy: %skWh, Sell: %skWh, PV: %skWh", 
                                    total.get("loadEnergy", "N/A"), 
                                    total.get("buyEnergy", "N/A"),
                                    total.get("sellEnergy", "N/A"),
                                    total.get("pvEnergy", "N/A"))
                                    
                        return result
            
            _LOGGER.warning("No load monitoring data points found for plant %s", plant_id)
            return None
            
        except asyncio.TimeoutError:
            _LOGGER.error("Timeout getting load monitoring data for plant %s", plant_id)
            return None
        except aiohttp.ClientError as ex:
            _LOGGER.error("HTTP error getting load monitoring data for plant %s: %s", plant_id, ex)
            return None
        except Exception as ex:
            _LOGGER.error("Error getting load monitoring data for plant %s: %s", plant_id, ex)
            return None

    async def get_device_data(self, device: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Get all data for a device."""
        device_sn = device["sn"]
        plant_id = device["plant_id"]
        device_type = device["type"]
        device_name = device.get("name", device_sn)

        _LOGGER.info("Fetching all data for %s device '%s' (SN: %s, Plant: %s)",
                    device_type, device_name, device_sn, plant_id)

        # Get different types of data based on device type
        plant_stats = await self.get_plant_statistics(plant_id)
        device_info = await self.get_device_details(device_sn)
        
        # Always fetch load monitoring data for solar devices (works 24/7)
        load_monitoring = None
        if device_type == DEVICE_TYPE_SOLAR:
            _LOGGER.debug("Fetching load monitoring data for solar device %s", device_sn)
            load_monitoring = await self.get_load_monitoring_data(plant_id)
        elif device_type != DEVICE_TYPE_BATTERY:
            # For other non-battery devices
            _LOGGER.debug("Fetching load monitoring data for non-battery device %s", device_sn)
            load_monitoring = await self.get_load_monitoring_data(plant_id)

        # For battery devices, use only realtime data
        # For solar devices, try both realtime and history data, but don't fail if they're unavailable
        history_data = None
        realtime_data = None
        
        if device_type == DEVICE_TYPE_BATTERY:
            # Battery devices use realtime data exclusively
            _LOGGER.debug("Fetching realtime data for battery device %s", device_sn)
            realtime_data = await self.get_realtime_data(device_sn)
            if not realtime_data:
                _LOGGER.error("Failed to get realtime data for battery device %s", device_sn)
                return None
        elif device_type == DEVICE_TYPE_SOLAR:
            # Solar devices - try to get both realtime and history data
            # But don't fail if they're unavailable (nighttime operation)
            _LOGGER.debug("Fetching both realtime and history data for solar device %s", device_sn)
            realtime_data = await self.get_realtime_data(device_sn)
            history_data = await self.get_history_data(device_sn, plant_id)
            
            # For solar devices at night, both realtime and history might be unavailable
            # That's okay, we'll use load monitoring data
            if not history_data and not realtime_data:
                _LOGGER.info("Both realtime and history data unavailable for solar device %s - likely nighttime", device_sn)
                # Make sure we have at least load monitoring data
                if not load_monitoring:
                    _LOGGER.error("No data available for solar device %s", device_sn)
                    return None
        else:
            # Other non-battery, non-solar devices use history data
            _LOGGER.debug("Fetching history data for device %s", device_sn)
            history_data = await self.get_history_data(device_sn, plant_id)
            if not history_data:
                _LOGGER.error("Failed to get history data for device %s", device_sn)
                return None

        # Process data based on device type and available data
        # For solar, use realtime data if available, then history data, then load monitoring
        is_realtime = False
        data_to_process = None
        
        if device_type == DEVICE_TYPE_BATTERY:
            is_realtime = True
            data_to_process = realtime_data
            _LOGGER.debug("Using realtime data for battery device %s", device_sn)
        elif device_type == DEVICE_TYPE_SOLAR:
            # For solar, prioritize data sources
            if realtime_data and realtime_data.get("isOnline") == "1":
                is_realtime = True
                data_to_process = realtime_data
                _LOGGER.debug("Using realtime data for solar device %s", device_sn)
            elif history_data:
                is_realtime = False
                data_to_process = history_data
                _LOGGER.debug("Using history data for solar device %s", device_sn)
            else:
                # No realtime or history data available (nighttime)
                # We'll use an empty dict and rely on load monitoring data
                is_realtime = False
                data_to_process = {}
                _LOGGER.debug("Using empty data for solar device %s (nighttime)", device_sn)
        else:
            # Other device types
            is_realtime = False
            data_to_process = history_data
            _LOGGER.debug("Using history data for device %s", device_sn)
        
        # Process the data to create calculated fields based on device type
        processed_data = self._process_device_data(
            data_to_process, 
            plant_stats, 
            device_type, 
            is_realtime=is_realtime,
            load_monitoring=load_monitoring,  # Pass load monitoring data for nighttime operation
            device_sn=device_sn               # Pass device_sn for better logging
        )
        
        # Combine all data into a single dictionary
        result = {
            "device_info": device_info,
            "plant_stats": plant_stats,
            "history_data": history_data,
            "realtime_data": realtime_data,  # Add realtime_data to the result
            "load_monitoring": load_monitoring,
            "device_type": device_type,
            "processed_data": processed_data,
        }
        
        _LOGGER.info("Successfully retrieved and processed data for %s device %s", device_type, device_sn)
        return result
    
    def _log_data_with_classification(self, category: str, data_source: str, field_name: str, value: Any, device_sn: str):
        """Helper method to log data with consistent formatting and classification."""
        _LOGGER.debug("[%s device %s] %s data %s: %s", 
                     data_source.upper(), device_sn, category, field_name, value)
    
    def _log_data_section(self, category: str, device_type: str, data_source: str, device_sn: str):
        """Log the beginning of a data section with consistent formatting."""
        _LOGGER.debug("[%s device %s] Processing %s %s data", 
                     device_type.upper(), device_sn, data_source, category)
    
    def _process_battery_realtime_data(self, data: Dict[str, Any], device_sn: str) -> Dict[str, Any]:
        """Process realtime data from battery devices."""
        processed = {}
        
        try:
            # Log device type
            _LOGGER.debug("[BATTERY device %s] Processing realtime data", device_sn)
            
            # Group data for structured logging
            data_categories = {
                "GRID": ['sysGridPowerWatt', 'gridDirection', 'todaySellEnergy', 'todayFeedInEnergy',
                        'totalSellEnergy', 'totalFeedInEnergy'],
                "BATTERY": ['batPower', 'batEnergyPercent', 'batteryDirection', 'todayBatChgEnergy', 
                           'todayBatDisEnergy', 'totalBatChgEnergy', 'totalBatDisEnergy', 'batTempC'],
                "LOAD": ['sysTotalLoadWatt', 'todayLoadEnergy', 'totalTotalLoadEnergy'],
                "PV": ['todayPvEnergy', 'totalPvEnergy', 'totalPVPower'],
                "TEMPERATURE": ['batTempC', 'sinkTempC'],
                "OPERATING": ['mpvMode']
            }
            
            # Log data by category (only in debug mode to avoid excessive logs)
            for category, fields in data_categories.items():
                self._log_data_section(category, "battery", "realtime", device_sn)
                for field in fields:
                    if field in data:
                        self._log_data_with_classification(category, "battery", field, data.get(field), device_sn)
            
            # Process grid data
            grid_power = float(data.get('sysGridPowerWatt', 0))
            processed["grid_power_abs"] = abs(grid_power)
            # Grid direction based on gridDirection (1 for exporting/selling, -1 for importing/feeding in)
            grid_direction_value = int(data.get('gridDirection', 0))
            grid_direction = "exporting" if grid_direction_value == 1 else "importing" if grid_direction_value == -1 else "idle"
            processed["grid_status_calculated"] = grid_direction

            # Home load from sysTotalLoadWatt
            processed["home_load_power"] = float(data.get('sysTotalLoadWatt', 0))
            
            # Battery data
            bat_power = float(data.get('batPower', 0))
            bat_level = float(data.get('batEnergyPercent', 0))
            processed["battery_level"] = bat_level
            processed["battery_power_abs"] = abs(bat_power)
            
            # Battery status from batteryDirection (0 for idle)
            bat_direction = int(data.get('batteryDirection', 0))
            if bat_direction == 0:
                bat_status = "Standby"
            else:
                bat_status = "Discharging" if bat_power > 0 else "Charging"
            processed["battery_status_calculated"] = bat_status
            
            # Temperature values
            if "batTempC" in data and data["batTempC"] != "0":
                processed["battery_temp"] = float(data["batTempC"])
            if "sinkTempC" in data and data["sinkTempC"] != "0":
                processed["sink_temp"] = float(data["sinkTempC"])

            # Energy values
            processed["today_battery_charge"] = float(data.get('todayBatChgEnergy', 0))
            processed["today_battery_discharge"] = float(data.get('todayBatDisEnergy', 0))
            
            # Store total battery energy values
            if 'totalBatChgEnergy' in data:
                processed["total_battery_charge"] = float(data.get('totalBatChgEnergy', 0))
            if 'totalBatDisEnergy' in data:
                processed["total_battery_discharge"] = float(data.get('totalBatDisEnergy', 0))
            
            processed["today_load_energy"] = float(data.get('todayLoadEnergy', 0))
            processed["today_pv_energy"] = float(data.get('todayPvEnergy', 0))
            processed["total_pv_energy"] = float(data.get('totalPvEnergy', 0))
            
            # Process current PV power from totalPVPower field
            if 'totalPVPower' in data:
                try:
                    processed["total_pv_power_calculated"] = float(data.get('totalPVPower', 0))
                except (ValueError, TypeError):
                    _LOGGER.warning("[BATTERY device %s] Could not convert totalPVPower value to float: %s", 
                                   device_sn, data.get('totalPVPower'))
            
            # Grid energy exchange values
            processed["today_grid_export_energy"] = float(data.get('todaySellEnergy', 0))
            processed["today_grid_import_energy"] = float(data.get('todayFeedInEnergy', 0))
            
            # Add total grid export energy if available
            if 'totalSellEnergy' in data:
                try:
                    processed["total_grid_export"] = float(data.get('totalSellEnergy', 0))
                except (ValueError, TypeError):
                    _LOGGER.warning("[BATTERY device %s] Could not convert totalSellEnergy value to float: %s", 
                                   device_sn, data.get('totalSellEnergy'))
            
            # Add total grid import energy if available
            if 'totalFeedInEnergy' in data:
                try:
                    processed["total_grid_import"] = float(data.get('totalFeedInEnergy', 0))
                except (ValueError, TypeError):
                    _LOGGER.warning("[BATTERY device %s] Could not convert totalFeedInEnergy value to float: %s", 
                                   device_sn, data.get('totalFeedInEnergy'))
            
            # Add total load energy if available
            if 'totalTotalLoadEnergy' in data:
                try:
                    processed["total_load_energy"] = float(data.get('totalTotalLoadEnergy', 0))
                except (ValueError, TypeError):
                    _LOGGER.warning("[BATTERY device %s] Could not convert totalTotalLoadEnergy value to float: %s", 
                                   device_sn, data.get('totalTotalLoadEnergy'))
            
            # Add operating mode/status from mpvMode if available
            if 'mpvMode' in data:
                try:
                    mpv_mode = int(data.get('mpvMode', 0))
                    processed["operating_mode"] = mpv_mode
                    processed["operating_status"] = mpv_mode
                except (ValueError, TypeError):
                    _LOGGER.warning("[BATTERY device %s] Could not convert mpvMode value to int: %s", 
                                   device_sn, data.get('mpvMode'))
            
            # Calculate estimated annual production and savings
            if 'todayPvEnergy' in data:
                try:
                    today_energy = float(data.get('todayPvEnergy', 0))
                    days_passed = dt_util.now().timetuple().tm_yday  # Day of the year
                    if days_passed > 0:
                        processed["estimated_annual_production"] = today_energy / days_passed * 365
                        # Estimate financial savings (using $0.15/kWh as an example)
                        processed["estimated_annual_savings"] = processed["estimated_annual_production"] * 0.15
                except (ValueError, TypeError, ZeroDivisionError):
                    pass

            # Log summary of processed data
            _LOGGER.debug("[BATTERY device %s] Processing complete - key metrics: Grid: %sW (%s), Battery: %s%% (%s @ %sW), Load: %sW", 
                         device_sn,
                         processed.get("grid_power_abs", "N/A"), 
                         processed.get("grid_status_calculated", "N/A"),
                         processed.get("battery_level", "N/A"),
                         processed.get("battery_status_calculated", "N/A"),
                         processed.get("battery_power_abs", "N/A"),
                         processed.get("home_load_power", "N/A"))

            return processed

        except (ValueError, TypeError) as ex:
            _LOGGER.error("[BATTERY device %s] Error processing realtime data: %s", device_sn, ex)
            return processed
    
    def _process_solar_data(self, data: Dict[str, Any], is_realtime: bool, is_nighttime: bool, 
                           load_monitoring: Dict[str, Any], plant_stats: Dict[str, Any], 
                           device_sn: str) -> Dict[str, Any]:
        """Process data from solar devices with special handling for nighttime."""
        processed = {}
        
        # Log operation mode
        if is_nighttime:
            _LOGGER.debug("[SOLAR device %s] Processing nighttime data", device_sn)
        else:
            _LOGGER.debug("[SOLAR device %s] Processing %s data", 
                         device_sn, "realtime" if is_realtime else "history")
        
        # Process PV data - set to 0 during nighttime
        self._log_data_section("PV", "solar", "processing", device_sn)
        
        if is_nighttime:
            # During nighttime, all PV values are 0
            processed["total_pv_power_calculated"] = 0
            for i in range(1, 3):  # Just PV1 and PV2
                # Set power, voltage, and current to 0 for PV1 and PV2
                processed[f"pv{i}_power"] = 0
                processed[f"pv{i}_voltage"] = 0
                processed[f"pv{i}_current"] = 0
            _LOGGER.debug("[SOLAR device %s] Nighttime operation - PV1 and PV2 values set to 0", device_sn)
            
            # Set grid phase values to 0 during nighttime
            for phase in ["r", "s", "t"]:
                processed[f"{phase}_phase_power"] = 0
                processed[f"{phase}_phase_voltage"] = 0
                processed[f"{phase}_phase_current"] = 0
                processed[f"{phase}_phase_frequency"] = 0
            _LOGGER.debug("[SOLAR device %s] Nighttime operation - Grid phase values set to 0", device_sn)
            
            # Set default operating mode during nighttime
            processed["operating_mode"] = 0
            processed["operating_status"] = 1  # 1 = Waiting (Standby)
            _LOGGER.debug("[SOLAR device %s] Nighttime operation - Operating mode set to 0, status set to 1 (Standby)", device_sn)
        else:
            # Normal daytime operation - process PV data
            total_pv_power = 0
            for i in range(1, 17):  # Check all possible PV inputs
                pv_power_key = f"pv{i}power"
                if pv_power_key in data and data[pv_power_key]:
                    self._log_data_with_classification("PV", "solar", pv_power_key, data.get(pv_power_key), device_sn)
                    try:
                        pv_power = float(data[pv_power_key])
                        total_pv_power += pv_power
                        processed[f"pv{i}_power"] = pv_power
                    except (ValueError, TypeError):
                        _LOGGER.warning("[SOLAR device %s] Could not convert %s to float: %s", 
                                      device_sn, pv_power_key, data.get(pv_power_key))
            
            # Process PV voltage and current if available
            for i in range(1, 17):  # Check all possible PV inputs
                pv_volt_key = f"pv{i}volt"
                pv_curr_key = f"pv{i}curr"
                
                if pv_volt_key in data and data[pv_volt_key]:
                    try:
                        processed[f"pv{i}_voltage"] = float(data[pv_volt_key])
                        self._log_data_with_classification("PV", "solar", pv_volt_key, data.get(pv_volt_key), device_sn)
                    except (ValueError, TypeError):
                        _LOGGER.warning("[SOLAR device %s] Could not convert %s to float: %s", 
                                      device_sn, pv_volt_key, data.get(pv_volt_key))
                
                if pv_curr_key in data and data[pv_curr_key]:
                    try:
                        processed[f"pv{i}_current"] = float(data[pv_curr_key])
                        self._log_data_with_classification("PV", "solar", pv_curr_key, data.get(pv_curr_key), device_sn)
                    except (ValueError, TypeError):
                        _LOGGER.warning("[SOLAR device %s] Could not convert %s to float: %s", 
                                      device_sn, pv_curr_key, data.get(pv_curr_key))
            
            # Check if totalPVPower is available in the data
            if "totalPVPower" in data:
                self._log_data_with_classification("PV", "solar", "totalPVPower", data.get("totalPVPower"), device_sn)
                
                # Try to use totalPVPower from data if it's not zero
                try:
                    reported_total = float(data.get("totalPVPower", 0))
                    if reported_total > 0:
                        processed["total_pv_power_calculated"] = reported_total
                    else:
                        # If totalPVPower is 0 but we calculated a non-zero sum, use our calculation
                        processed["total_pv_power_calculated"] = total_pv_power if total_pv_power > 0 else 0
                except (ValueError, TypeError):
                    # If conversion fails, use our calculated sum
                    processed["total_pv_power_calculated"] = total_pv_power if total_pv_power > 0 else 0
            else:
                # If totalPVPower is not in the data, use our calculated sum
                processed["total_pv_power_calculated"] = total_pv_power if total_pv_power > 0 else 0
                
            _LOGGER.debug("[SOLAR device %s] Total PV power calculated: %sW", 
                         device_sn, processed.get("total_pv_power_calculated", 0))
            
            # Process phase data if available
            self._log_data_section("PHASE", "solar", "processing", device_sn)
            try:
                total_phase_power = 0
                for phase in ["r", "s", "t"]:
                    phase_power_key = f"{phase}GridPowerWatt"
                    phase_volt_key = f"{phase}GridVolt"
                    phase_curr_key = f"{phase}GridCurr"
                    phase_freq_key = f"{phase}GridFreq"
                    
                    if phase_power_key in data and data[phase_power_key]:
                        self._log_data_with_classification("PHASE", "solar", phase_power_key, data.get(phase_power_key), device_sn)
                        phase_power = float(data[phase_power_key])
                        total_phase_power += phase_power
                        processed[f"{phase}_phase_power"] = phase_power
                    
                    if phase_volt_key in data and data[phase_volt_key]:
                        self._log_data_with_classification("PHASE", "solar", phase_volt_key, data.get(phase_volt_key), device_sn)
                        processed[f"{phase}_phase_voltage"] = float(data[phase_volt_key])
                    
                    if phase_curr_key in data and data[phase_curr_key]:
                        self._log_data_with_classification("PHASE", "solar", phase_curr_key, data.get(phase_curr_key), device_sn)
                        processed[f"{phase}_phase_current"] = float(data[phase_curr_key])
                        
                    if phase_freq_key in data and data[phase_freq_key]:
                        self._log_data_with_classification("PHASE", "solar", phase_freq_key, data.get(phase_freq_key), device_sn)
                        processed[f"{phase}_phase_frequency"] = float(data[phase_freq_key])
                        
                processed["total_phase_power"] = total_phase_power
                _LOGGER.debug("[SOLAR device %s] Total phase power: %sW", device_sn, total_phase_power)
            except (ValueError, TypeError) as ex:
                _LOGGER.warning("[SOLAR device %s] Error processing phase data: %s", device_sn, ex)
            
            # Process temperature data
            self._log_data_section("TEMPERATURE", "solar", "processing", device_sn)
            if "invTempC" in data:
                self._log_data_with_classification("TEMPERATURE", "solar", "invTempC", data.get("invTempC"), device_sn)
            if "sinkTempC" in data:
                self._log_data_with_classification("TEMPERATURE", "solar", "sinkTempC", data.get("sinkTempC"), device_sn)
                
            try:
                if "invTempC" in data and data["invTempC"]:
                    processed["inverter_temp"] = float(data["invTempC"])
                if "sinkTempC" in data and data["sinkTempC"]:
                    processed["sink_temp"] = float(data["sinkTempC"])
            except (ValueError, TypeError) as ex:
                _LOGGER.warning("[SOLAR device %s] Error processing temperature data: %s", device_sn, ex)
        
        # Process grid data - prioritize load monitoring data
        self._log_data_section("GRID", "solar", "processing", device_sn)
        if load_monitoring:
            # Use load monitoring data for grid power (works 24/7)
            latest = load_monitoring.get("latest", {})
            if "buyPower" in latest and "sellPower" in latest:
                try:
                    buy_power = float(latest.get("buyPower", 0))
                    sell_power = float(latest.get("sellPower", 0))
                    
                    # Net grid power (positive = importing, negative = exporting)
                    grid_power = buy_power - sell_power
                    
                    self._log_data_with_classification("GRID", "solar", "buyPower", buy_power, device_sn)
                    self._log_data_with_classification("GRID", "solar", "sellPower", sell_power, device_sn)
                    self._log_data_with_classification("GRID", "solar", "calculatedGridPower", grid_power, device_sn)
                    
                    grid_direction = "exporting" if grid_power < 0 else "importing" if grid_power > 0 else "idle"
                    processed["grid_status_calculated"] = grid_direction
                    processed["grid_power_abs"] = abs(grid_power)
                    
                    _LOGGER.debug("[SOLAR device %s] Grid status from load monitoring: %s @ %sW", 
                                 device_sn, grid_direction, abs(grid_power))
                except (ValueError, TypeError) as ex:
                    _LOGGER.warning("[SOLAR device %s] Error processing grid power from load monitoring: %s", device_sn, ex)
        elif not is_nighttime:
            # Fall back to realtime/history data if load monitoring is unavailable
            if "totalGridPowerWatt" in data:
                self._log_data_with_classification("GRID", "solar", "totalGridPowerWatt", data.get("totalGridPowerWatt"), device_sn)
                try:
                    grid_power = float(data.get('totalGridPowerWatt', 0))
                    grid_direction = "exporting" if grid_power < 0 else "importing" if grid_power > 0 else "idle"
                    processed["grid_status_calculated"] = grid_direction
                    processed["grid_power_abs"] = abs(grid_power)
                    
                    _LOGGER.debug("[SOLAR device %s] Grid status from %s data: %s @ %sW", 
                                 device_sn, "realtime" if is_realtime else "history", 
                                 grid_direction, abs(grid_power))
                except (ValueError, TypeError) as ex:
                    _LOGGER.warning("[SOLAR device %s] Error processing grid power from data: %s", device_sn, ex)
        
        # Process home load power - prioritize load monitoring data
        self._log_data_section("LOAD", "solar", "processing", device_sn)
        if load_monitoring:
            # Use load monitoring data for home load (works 24/7)
            latest = load_monitoring.get("latest", {})
            if "loadPower" in latest:
                try:
                    load_power = float(latest.get("loadPower", 0))
                    self._log_data_with_classification("LOAD", "solar", "loadPower", load_power, device_sn)
                    processed["home_load_power"] = load_power
                    
                    _LOGGER.debug("[SOLAR device %s] Home load power from load monitoring: %sW", device_sn, load_power)
                except (ValueError, TypeError) as ex:
                    _LOGGER.warning("[SOLAR device %s] Error processing load power from load monitoring: %s", device_sn, ex)
        elif not is_nighttime and "totalLoadPowerWatt" in data:
            # Fall back to realtime/history data if load monitoring is unavailable
            self._log_data_with_classification("LOAD", "solar", "totalLoadPowerWatt", data.get("totalLoadPowerWatt"), device_sn)
            try:
                load_power = float(data.get("totalLoadPowerWatt", 0))
                processed["home_load_power"] = load_power
                
                _LOGGER.debug("[SOLAR device %s] Home load power from %s data: %sW", 
                             device_sn, "realtime" if is_realtime else "history", load_power)
            except (ValueError, TypeError) as ex:
                _LOGGER.warning("[SOLAR device %s] Error processing load power from data: %s", device_sn, ex)
        
        # Process plant statistics data (always available)
        if plant_stats:
            self._log_data_section("PLANT", "solar", "processing", device_sn)
            
            if "totalReduceCo2" in plant_stats:
                self._log_data_with_classification("PLANT", "solar", "totalReduceCo2", plant_stats.get("totalReduceCo2"), device_sn)
            if "totalPlantTreeNum" in plant_stats:
                self._log_data_with_classification("PLANT", "solar", "totalPlantTreeNum", plant_stats.get("totalPlantTreeNum"), device_sn)
            if "yearPvEnergy" in plant_stats:
                self._log_data_with_classification("PLANT", "solar", "yearPvEnergy", plant_stats.get("yearPvEnergy"), device_sn)
                
            try:
                # Environmental impact
                if "totalReduceCo2" in plant_stats:
                    processed["co2_reduction"] = float(plant_stats["totalReduceCo2"])
                if "totalPlantTreeNum" in plant_stats:
                    processed["equivalent_trees"] = float(plant_stats["totalPlantTreeNum"])
                    
                # Annual projections
                if "yearPvEnergy" in plant_stats:
                    year_energy = float(plant_stats["yearPvEnergy"])
                    days_passed = dt_util.now().timetuple().tm_yday  # Day of the year
                    if days_passed > 0:
                        processed["estimated_annual_production"] = year_energy / days_passed * 365
                        # Estimate financial savings (using $0.15/kWh as an example)
                        processed["estimated_annual_savings"] = processed["estimated_annual_production"] * 0.15
                        
                        _LOGGER.debug("[SOLAR device %s] Annual estimates - Production: %.2f kWh, Savings: $%.2f", 
                                     device_sn, processed["estimated_annual_production"], processed["estimated_annual_savings"])
            except (ValueError, TypeError, ZeroDivisionError) as ex:
                _LOGGER.warning("[SOLAR device %s] Error processing plant statistics: %s", device_sn, ex)
        
        # Process energy data - set to 0 during nighttime for today's values
        self._log_data_section("ENERGY", "solar", "processing", device_sn)
        
        if is_nighttime:
            processed["today_pv_energy"] = 0
            _LOGGER.debug("[SOLAR device %s] Nighttime operation - today's PV energy set to 0", device_sn)
        elif "todayPvEnergy" in data:
            self._log_data_with_classification("ENERGY", "solar", "todayPvEnergy", data.get("todayPvEnergy"), device_sn)
            try:
                processed["today_pv_energy"] = float(data["todayPvEnergy"])
            except (ValueError, TypeError):
                processed["today_pv_energy"] = 0
        
        # Total energy values should still be available from plant stats
        if "totalPvEnergy" in data:
            self._log_data_with_classification("ENERGY", "solar", "totalPvEnergy", data.get("totalPvEnergy"), device_sn)
            try:
                processed["total_pv_energy"] = float(data["totalPvEnergy"])
            except (ValueError, TypeError):
                pass
        elif plant_stats and "totalPvEnergy" in plant_stats:
            try:
                processed["total_pv_energy"] = float(plant_stats["totalPvEnergy"])
            except (ValueError, TypeError):
                pass
        
        # Process grid export/import data
        if is_nighttime:
            processed["today_grid_export_energy"] = 0
            _LOGGER.debug("[SOLAR device %s] Nighttime operation - today's grid export energy set to 0", device_sn)
        elif "todaySellEnergy" in data:
            self._log_data_with_classification("ENERGY", "solar", "todaySellEnergy", data.get("todaySellEnergy"), device_sn)
            try:
                processed["today_grid_export_energy"] = float(data["todaySellEnergy"])
            except (ValueError, TypeError):
                processed["today_grid_export_energy"] = 0
        
        # Total grid export should still be available
        if "totalSellEnergy" in data:
            self._log_data_with_classification("ENERGY", "solar", "totalSellEnergy", data.get("totalSellEnergy"), device_sn)
            try:
                processed["total_grid_export"] = float(data["totalSellEnergy"])
            except (ValueError, TypeError):
                pass
        elif plant_stats and "totalSellEnergy" in plant_stats:
            try:
                processed["total_grid_export"] = float(plant_stats["totalSellEnergy"])
            except (ValueError, TypeError):
                pass
        
        # Process load monitoring energy data (works 24/7)
        if load_monitoring:
            total_values = load_monitoring.get("total", {})
            
            # Log the energy values
            if "buyEnergy" in total_values:
                self._log_data_with_classification("ENERGY", "solar", "buyEnergy", total_values.get("buyEnergy"), device_sn)
            if "sellEnergy" in total_values:
                self._log_data_with_classification("ENERGY", "solar", "sellEnergy", total_values.get("sellEnergy"), device_sn)
            if "pvEnergy" in total_values:
                self._log_data_with_classification("ENERGY", "solar", "pvEnergy", total_values.get("pvEnergy"), device_sn)
            if "loadEnergy" in total_values:
                self._log_data_with_classification("ENERGY", "solar", "loadEnergy", total_values.get("loadEnergy"), device_sn)
            
            if "pvEnergy" in total_values:
                try:
                    pv_energy = float(total_values["pvEnergy"])
                    processed["today_pv_energy"] = pv_energy
                    _LOGGER.debug("[SOLAR device %s] Today's PV energy from load monitoring: %.2f kWh", device_sn, pv_energy)
                except (ValueError, TypeError):
                    pass
            
            if "loadEnergy" in total_values:
                try:
                    processed["total_load_energy"] = float(total_values["loadEnergy"])
                except (ValueError, TypeError):
                    pass
            
            if "buyEnergy" in total_values:
                try:
                    processed["total_grid_import"] = float(total_values["buyEnergy"])
                    processed["today_grid_import_energy"] = float(total_values["buyEnergy"])
                except (ValueError, TypeError):
                    pass
            
            if "sellEnergy" in total_values:
                try:
                    # Double-check this against total_grid_export
                    sell_energy = float(total_values["sellEnergy"])
                    if "total_grid_export" not in processed:
                        processed["total_grid_export"] = sell_energy
                    processed["today_grid_export_energy"] = sell_energy
                except (ValueError, TypeError):
                    pass
        
        # Log summary of processed data
        _LOGGER.debug("[SOLAR device %s] Processing complete - key metrics: PV: %sW, Grid: %sW (%s), Load: %sW", 
                     device_sn,
                     processed.get("total_pv_power_calculated", "N/A"), 
                     processed.get("grid_power_abs", "N/A"),
                     processed.get("grid_status_calculated", "N/A"),
                     processed.get("home_load_power", "N/A"))
        
        return processed
        
    def _process_device_data(self, data, plant_stats, device_type, is_realtime=False, 
                            load_monitoring=None, device_sn="unknown"):
        """Process device data to create calculated fields."""
        processed = {}
        
        if not data and device_type != DEVICE_TYPE_SOLAR:
            _LOGGER.warning("[%s device %s] No data to process", device_type.upper(), device_sn)
            return processed

        # For battery devices with realtime data, use dedicated processor
        if is_realtime and device_type == DEVICE_TYPE_BATTERY:
            return self._process_battery_realtime_data(data, device_sn)
            
        # For solar devices, process data with special handling for nighttime
        if device_type == DEVICE_TYPE_SOLAR:
            # Check if we're likely in nighttime mode (empty data)
            is_nighttime = not data or (is_realtime and data.get("isOnline") != "1")
            return self._process_solar_data(data, is_realtime, is_nighttime, load_monitoring, plant_stats, device_sn)
            
        # For battery device using history data (rare)
        if device_type == DEVICE_TYPE_BATTERY:
            _LOGGER.debug("[BATTERY device %s] Processing history data", device_sn)
            
            self._log_data_section("BATTERY", "battery", "history", device_sn)
            if "batPower" in data:
                self._log_data_with_classification("BATTERY", "battery", "batPower", data.get("batPower"), device_sn)
            if "batEnergyPercent" in data:
                self._log_data_with_classification("BATTERY", "battery", "batEnergyPercent", data.get("batEnergyPercent"), device_sn)
                
            try:
                bat_power = float(data.get("batPower", 0))
                if bat_power > 0:
                    bat_status = "Discharging"
                elif bat_power < 0:
                    bat_status = "Charging"
                else:
                    bat_status = "Standby"
                processed["battery_status_calculated"] = bat_status
                processed["battery_power_abs"] = abs(bat_power)
                
                _LOGGER.debug("[BATTERY device %s] Battery status from history data: %s @ %sW", 
                             device_sn, bat_status, abs(bat_power))
            except (ValueError, TypeError) as ex:
                _LOGGER.warning("[BATTERY device %s] Error processing battery data: %s", device_sn, ex)
                
        # Process temperature data for all device types
        if "invTempC" in data or "sinkTempC" in data:
            self._log_data_section("TEMPERATURE", device_type, "processing", device_sn)
            
            if "invTempC" in data:
                self._log_data_with_classification("TEMPERATURE", device_type, "invTempC", data.get("invTempC"), device_sn)
            if "sinkTempC" in data:
                self._log_data_with_classification("TEMPERATURE", device_type, "sinkTempC", data.get("sinkTempC"), device_sn)
                
            try:
                if "invTempC" in data and data["invTempC"]:
                    processed["inverter_temp"] = float(data["invTempC"])
                if "sinkTempC" in data and data["sinkTempC"]:
                    processed["sink_temp"] = float(data["sinkTempC"])
            except (ValueError, TypeError) as ex:
                _LOGGER.warning("[%s device %s] Error processing temperature data: %s", device_type.upper(), device_sn, ex)
            
        # Process plant statistics data for all device types
        if plant_stats:
            self._log_data_section("PLANT", device_type, "processing", device_sn)
            
            if "totalReduceCo2" in plant_stats:
                self._log_data_with_classification("PLANT", device_type, "totalReduceCo2", plant_stats.get("totalReduceCo2"), device_sn)
            if "totalPlantTreeNum" in plant_stats:
                self._log_data_with_classification("PLANT", device_type, "totalPlantTreeNum", plant_stats.get("totalPlantTreeNum"), device_sn)
            if "yearPvEnergy" in plant_stats:
                self._log_data_with_classification("PLANT", device_type, "yearPvEnergy", plant_stats.get("yearPvEnergy"), device_sn)
                
            try:
                # Environmental impact
                if "totalReduceCo2" in plant_stats:
                    processed["co2_reduction"] = float(plant_stats["totalReduceCo2"])
                if "totalPlantTreeNum" in plant_stats:
                    processed["equivalent_trees"] = float(plant_stats["totalPlantTreeNum"])
                    
                # Annual projections
                if "yearPvEnergy" in plant_stats:
                    year_energy = float(plant_stats["yearPvEnergy"])
                    days_passed = dt_util.now().timetuple().tm_yday  # Day of the year
                    if days_passed > 0:
                        processed["estimated_annual_production"] = year_energy / days_passed * 365
                        # Estimate financial savings (using $0.15/kWh as an example)
                        processed["estimated_annual_savings"] = processed["estimated_annual_production"] * 0.15
                        
                        _LOGGER.debug("[%s device %s] Annual estimates - Production: %.2f kWh, Savings: $%.2f", 
                                     device_type.upper(), device_sn, 
                                     processed["estimated_annual_production"], 
                                     processed["estimated_annual_savings"])
            except (ValueError, TypeError, ZeroDivisionError) as ex:
                _LOGGER.warning("[%s device %s] Error processing plant statistics: %s", device_type.upper(), device_sn, ex)
                
        _LOGGER.debug("[%s device %s] Processing complete", device_type.upper(), device_sn)
        return processed