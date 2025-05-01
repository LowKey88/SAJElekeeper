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
        self._token_expires_at = datetime.now()
        
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
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            stats_url = f"{BASE_URL}{PLANT_STATS_URL}"
            stats_params = {"plantId": plant_id, "clientDate": now}
            # Include Content-Type header for plant statistics
            stats_headers = {
                "accessToken": token,
                "content-language": "en_US",
                "Content-Type": "application/json"
            }

            async with async_timeout.timeout(10):
                stats_resp = await self._session.get(stats_url, params=stats_params, headers=stats_headers)
                stats_json = await stats_resp.json()

            if stats_json.get("code") != 200 or "data" not in stats_json:
                _LOGGER.error("Error in plant statistics response: %s", stats_json.get("msg", "Unknown error"))
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

    async def get_history_data(self, device_sn: str, plant_id: str) -> Optional[Dict[str, Any]]:
        """Get historical data from SAJ API."""
        token = await self._get_token()
        if not token:
            return None

        try:
            end_time = datetime.now()
            start_time = end_time - timedelta(minutes=10)  # Use last 10 minutes for more recent data

            start_time_str = start_time.strftime("%Y-%m-%d %H:%M:%S")
            end_time_str = end_time.strftime("%Y-%m-%d %H:%M:%S")

            history_url = f"{BASE_URL}{HISTORY_DATA_URL}"
            history_params = {
                "deviceSn": device_sn,
                "plantId": plant_id,  # Include plantId for better reliability
                "startTime": start_time_str,
                "endTime": end_time_str
            }
            
            history_headers = {
                "accessToken": token,
                "content-language": "en_US",
            }

            async with async_timeout.timeout(10):
                history_resp = await self._session.get(history_url, params=history_params, headers=history_headers)
                history_json = await history_resp.json()

            if history_json.get("code") != 200 or "data" not in history_json:
                _LOGGER.error("Error in history data response: %s", history_json.get("msg", "Unknown error"))
                return None

            history_data = history_json["data"]
            
            if not isinstance(history_data, list) or not history_data:
                _LOGGER.error("No history data points found in response")
                return None

            # Return the most recent data point (first in the list)
            return history_data[0]

        except asyncio.TimeoutError:
            _LOGGER.error("Timeout getting history data")
            return None
        except aiohttp.ClientError as ex:
            _LOGGER.error("HTTP error getting history data: %s", ex)
            return None
        except Exception as ex:
            _LOGGER.error("Error getting history data: %s", ex)
            return None

    async def get_realtime_data(self, device_sn: str) -> Optional[Dict[str, Any]]:
        """Get realtime data from SAJ API."""
        token = await self._get_token()
        if not token:
            return None

        try:
            realtime_url = f"{BASE_URL}{REALTIME_DATA_URL}"
            realtime_params = {"deviceSn": device_sn}
            realtime_headers = {
                "accessToken": token,
                "content-language": "en_US",
            }

            async with async_timeout.timeout(10):
                realtime_resp = await self._session.get(realtime_url, params=realtime_params, headers=realtime_headers)
                realtime_json = await realtime_resp.json()

            if realtime_json.get("code") != 200 or "data" not in realtime_json:
                _LOGGER.error("Error in realtime data response: %s", realtime_json.get("msg", "Unknown error"))
                return None

            return realtime_json["data"]

        except asyncio.TimeoutError:
            _LOGGER.error("Timeout getting realtime data")
            return None
        except aiohttp.ClientError as ex:
            _LOGGER.error("HTTP error getting realtime data: %s", ex)
            return None
        except Exception as ex:
            _LOGGER.error("Error getting realtime data: %s", ex)
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

        # Get different types of data based on device type
        plant_stats = await self.get_plant_statistics(plant_id)
        device_info = await self.get_device_details(device_sn)
        load_monitoring = await self.get_load_monitoring_data(plant_id)

        # For battery devices, use only realtime data
        # For non-battery devices, use history data
        history_data = None
        realtime_data = None
        
        if device_type == DEVICE_TYPE_BATTERY:
            # Battery devices use realtime data
            realtime_data = await self.get_realtime_data(device_sn)
            if not realtime_data:
                _LOGGER.error("Failed to get realtime data for battery device %s", device_sn)
                return None
        else:
            # Non-battery devices use history data
            history_data = await self.get_history_data(device_sn, plant_id)
            if not history_data:
                _LOGGER.error("Failed to get history data for device %s", device_sn)
                return None

        # Process data based on device type and available data
        data_to_process = realtime_data if device_type == DEVICE_TYPE_BATTERY else history_data
        processed_data = self._process_device_data(data_to_process, plant_stats, device_type, is_realtime=(device_type == DEVICE_TYPE_BATTERY))
        
        # Combine all data into a single dictionary
        return {
            "device_info": device_info,
            "plant_stats": plant_stats,
            "history_data": history_data,
            "load_monitoring": load_monitoring,
            "device_type": device_type,
            "processed_data": processed_data,
        }
    
    def _process_device_data(self, data, plant_stats, device_type, is_realtime=False):
        """Process device data to create calculated fields."""
        processed = {}
        
        if not data:
            return processed

        if is_realtime and device_type == DEVICE_TYPE_BATTERY:
            # Use realtime data fields for battery devices
            try:
                # Log all battery-related fields for debugging
                _LOGGER.debug("Realtime data sysGridPowerWatt: %s", data.get('sysGridPowerWatt'))
                _LOGGER.debug("Realtime data gridDirection: %s", data.get('gridDirection'))
                _LOGGER.debug("Realtime data sysTotalLoadWatt: %s", data.get('sysTotalLoadWatt'))
                _LOGGER.debug("Realtime data batPower: %s", data.get('batPower'))
                _LOGGER.debug("Realtime data batEnergyPercent: %s", data.get('batEnergyPercent'))
                _LOGGER.debug("Realtime data batteryDirection: %s", data.get('batteryDirection'))
                _LOGGER.debug("Realtime data batTempC: %s", data.get('batTempC'))
                _LOGGER.debug("Realtime data sinkTempC: %s", data.get('sinkTempC'))
                _LOGGER.debug("Realtime data todayBatChgEnergy: %s", data.get('todayBatChgEnergy'))
                _LOGGER.debug("Realtime data todayBatDisEnergy: %s", data.get('todayBatDisEnergy'))
                _LOGGER.debug("Realtime data totalBatChgEnergy: %s", data.get('totalBatChgEnergy'))
                _LOGGER.debug("Realtime data totalBatDisEnergy: %s", data.get('totalBatDisEnergy'))
                _LOGGER.debug("Realtime data todayLoadEnergy: %s", data.get('todayLoadEnergy'))
                _LOGGER.debug("Realtime data todayPvEnergy: %s", data.get('todayPvEnergy'))
                _LOGGER.debug("Realtime data totalPvEnergy: %s", data.get('totalPvEnergy'))
                _LOGGER.debug("Realtime data todaySellEnergy: %s", data.get('todaySellEnergy'))
                _LOGGER.debug("Realtime data todayFeedInEnergy: %s", data.get('todayFeedInEnergy'))

                # Grid power from sysGridPowerWatt
                grid_power = float(data.get('sysGridPowerWatt', 0))
                processed["grid_power_abs"] = abs(grid_power)
                # Grid direction based on gridDirection (-1 for exporting, 1 for importing)
                grid_direction_value = int(data.get('gridDirection', 0))
                grid_direction = "exporting" if grid_direction_value == -1 else "importing" if grid_direction_value == 1 else "idle"
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
                    bat_status = "idle"
                else:
                    bat_status = "discharging" if bat_power > 0 else "charging"
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
                
                # Grid energy exchange values
                processed["today_grid_export_energy"] = float(data.get('todaySellEnergy', 0))
                processed["today_grid_import_energy"] = float(data.get('todayFeedInEnergy', 0))

                return processed

            except (ValueError, TypeError) as ex:
                _LOGGER.error("Error processing realtime data: %s", ex)
                return processed
            
        # Process data fields using history data format
        
        # 1. PV power calculations
        total_pv_power = 0
        for i in range(1, 17):  # Check all possible PV inputs
            pv_power_key = f"pv{i}power"
            if pv_power_key in data and data[pv_power_key]:
                try:
                    pv_power = float(data[pv_power_key])
                    total_pv_power += pv_power
                    processed[f"pv{i}_power"] = pv_power
                except (ValueError, TypeError):
                    pass
                    
        processed["total_pv_power_calculated"] = total_pv_power
        
        # 2. Grid status and power
        try:
            grid_power = float(data.get('totalGridPowerWatt', 0))
            grid_direction = "exporting" if grid_power < 0 else "importing" if grid_power > 0 else "idle"
            processed["grid_status_calculated"] = grid_direction
            processed["grid_power_abs"] = abs(grid_power)
        except (ValueError, TypeError):
            pass
            
        # 3. Battery status (for battery devices)
        if device_type == DEVICE_TYPE_BATTERY:
            try:
                bat_power = float(data.get("batPower", 0))
                if bat_power > 0:
                    bat_status = "discharging"
                elif bat_power < 0:
                    bat_status = "charging"
                else:
                    bat_status = "idle"
                processed["battery_status_calculated"] = bat_status
                processed["battery_power_abs"] = abs(bat_power)
            except (ValueError, TypeError):
                pass
                
        # 4. Device type specific processing
        if device_type == DEVICE_TYPE_SOLAR:
            # For R6: Calculate combined phase values
            try:
                total_phase_power = 0
                for phase in ["r", "s", "t"]:
                    phase_power_key = f"{phase}GridPowerWatt"
                    if phase_power_key in data and data[phase_power_key]:
                        phase_power = float(data[phase_power_key])
                        total_phase_power += phase_power
                        processed[f"{phase}_phase_power"] = phase_power
                processed["total_phase_power"] = total_phase_power
            except (ValueError, TypeError):
                pass
                
        # 5. Temperature values
        try:
            if "invTempC" in data and data["invTempC"]:
                processed["inverter_temp"] = float(data["invTempC"])
            if "sinkTempC" in data and data["sinkTempC"]:
                processed["sink_temp"] = float(data["sinkTempC"])
        except (ValueError, TypeError):
            pass
            
        # 6. Process plant statistics data
        if plant_stats:
            try:
                # Environmental impact
                if "totalReduceCo2" in plant_stats:
                    processed["co2_reduction"] = float(plant_stats["totalReduceCo2"])
                if "totalPlantTreeNum" in plant_stats:
                    processed["equivalent_trees"] = float(plant_stats["totalPlantTreeNum"])
                    
                # Annual projections
                if "yearPvEnergy" in plant_stats:
                    year_energy = float(plant_stats["yearPvEnergy"])
                    days_passed = datetime.now().timetuple().tm_yday  # Day of the year
                    if days_passed > 0:
                        processed["estimated_annual_production"] = year_energy / days_passed * 365
                        # Estimate financial savings (using $0.15/kWh as an example)
                        processed["estimated_annual_savings"] = processed["estimated_annual_production"] * 0.15
            except (ValueError, TypeError, ZeroDivisionError):
                pass
                
        return processed
