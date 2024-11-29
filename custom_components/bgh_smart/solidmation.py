"""BGH Smart devices API client"""
from aiohttp import ClientSession
from aiohttp import (
    ClientConnectorError,
    ClientOSError,
    ClientSession,
    ClientTimeout,
    ServerDisconnectedError,
    TCPConnector,
)
import json

from .const import LOGGER

BASE_URL = {
    'myhabeetat': 'https://myhabeetatcloud-services.solidmation.com/',
    'bgh': 'https://bgh-services.solidmation.com'
}

FAN_MODE = {
    'low': 1,
    'medium': 2,
    'high': 3,
    'auto': 254,
    'no_change': 255
}

MODE = {
    'off': 0,
    'cool': 1,
    'heat': 2,
    'dry': 3,
    'fan_only': 4,
    'auto': 254,
    'no_change': 255
}

# COMMAND_SWING_HORIZONTAL = 0x51
# COMMAND_SWING_VERTICAL = 0x61
# COMMAND_TURBO = 0x71

SWING_MODE = {
    'off': 0,
    'on': 0x51,
    'horizontal': 0x51,
    'vertical': 0x61
}

PRESET_MODE = {
    'none': 0,
    'boost': 0x71
}
# Exceptions
class BaseBGHSmartException(Exception):
    """Base exception for BGH Smart integration."""
class BadRequestException(BaseBGHSmartException):
    """Bad request."""
class UnauthorizedException(BaseBGHSmartException):
    """Unauthorized."""
class UnknownException(BaseBGHSmartException):
    """Unknown exception."""
class UnsupportedHostException(BaseBGHSmartException):
    """Raised when API is not available on given host."""
class AuthenticationException(UnauthorizedException):
    """Raised when authentication is not correct."""
class InvalidSessionException(UnauthorizedException):
    """Raised when session is invalid."""
class LoginRetryErrorException(BaseBGHSmartException):
    """Raised when too many login retries are attempted."""
class LoginTimeoutException(BaseBGHSmartException):
    """Raised when a timeout is encountered during login."""
class SolidmationClient:
    """BGH client implementation"""

    def __init__(self, email, password, backend, websession: ClientSession):
        self.base_url = BASE_URL[backend]
        self.email = email
        self.password = password
        self.websession = websession
        self.token = None
        self.timeout = 10

    async def _post(self, endpoint, json):
        try:
            resp = await self.websession.request("post", endpoint, json=json, timeout=self.timeout)
            if resp.status == 400:
                result = await resp.text()
                raise BadRequestException(result)

            if resp.status == 404:
                result = await resp.text()
                raise UnsupportedHostException(result)

            if resp.status != 200:
                result = await resp.text()
                raise UnknownException(result)
            return resp
        except (
            ClientConnectorError,
            ClientOSError,
            ServerDisconnectedError,
        ) as e:
            raise ConnectionError(str(e)) from e

    async def async_login(self) -> None:
        endpoint = "%s/control/LoginPage.aspx/DoStandardLogin" % self.base_url
        try:
            resp = await self._post(endpoint, json={'user': self.email, 'password': self.password})
            self.token = (await resp.json())['d']
            if self.token == '':
                raise AuthenticationException()
        except TimeoutError as e:
            raise LoginTimeoutException(str(e)) from e

    async def _async_request(self, endpoint, payload=None):
        if payload is None:
            payload = {}
        if self.token is None:
            await self.async_login()
        if self.token == '':
            raise InvalidSessionException()
        payload['token'] = {'Token': self.token}
        return await self._post(endpoint, json=payload)

    async def _async_get_data_packets(self, home_id):
        endpoint = "%s/1.0/HomeCloudService.svc/GetDataPacket" % self.base_url
        payload = {
            'homeID': home_id,
            'serials': {
                'Home': 0,
                'Groups': 0,
                'Devices': 0,
                'Endpoints': 0,
                'EndpointValues': 0,
                'Scenes': 0,
                'Macros': 0,
                'Alarms': 0
            },
            'timeOut': 10000
        }
        resp = await self._async_request(endpoint, payload)
        return (await resp.json())['GetDataPacketResult']

    def _parse_devices(self, data):
        devices = {}

        if data['Endpoints'] is None:
            return devices

        for idx, endpoint in enumerate(data['Endpoints']):
            device = {
                'device_id': endpoint['EndpointID'],
                'device_name': endpoint['Description'],
                'device_data': data['Devices'][idx],  # type dict,
                'raw_data': data['EndpointValues'][idx]['Values'],
                'data': self._parse_raw_data(data['EndpointValues'][idx]['Values']),
                'endpoints_data': endpoint
            }
            device['data']['device_model'] = device['device_data']['DeviceModel']
            device['data']['device_serial_number'] = device['device_data']['Address']
            device['data']['available'] = device['device_data']['IsOnline']
            max_temp = self._find_value(device['endpoints_data']['Parameters'], 'SetpointMaxC', 'Name')
            device['data']['max_temp'] = float(max_temp) if max_temp else 30
            min_temp = self._find_value(device['endpoints_data']['Parameters'], 'SetpointMinC', 'Name')
            device['data']['min_temp'] = float(min_temp) if min_temp else 17

            devices[device['device_id']] = device

        return devices

    @staticmethod
    def _find_value(data, value, value_name = 'ValueType'):
        try:
            return next(item['Value'] for item in data if item[value_name] == value)
        except StopIteration:
            LOGGER.error("Value %s = %s not found in %s", value_name, value, data)
            return None

    @staticmethod
    def _parse_raw_data(data):
        if data is None:
            return {}

        temperature = SolidmationClient._find_value(data,13)
        if temperature:
            temperature = float(temperature)
            if temperature <= -50:
                temperature = None

        target_temperature = SolidmationClient._find_value(data,20)
        if target_temperature:
            target_temperature = float(target_temperature)
            if target_temperature == 255:
                target_temperature = 20

        fan_speed = SolidmationClient._find_value(data,15)
        if fan_speed:
            fan_speed = int(fan_speed)

        mode_id = SolidmationClient._find_value(data,14)
        if mode_id:
            mode_id = int(mode_id)

        swing_mode = SolidmationClient._find_value(data,18)
        if swing_mode:
            swing_mode = int(swing_mode)

        # preset_mode = SolidmationClient._find_value(data,18)
        # if preset_mode:
        #     preset_mode = int(preset_mode)
        return {
            'temperature': temperature,
            'target_temperature': target_temperature,
            'fan_speed': fan_speed,
            'mode_id': mode_id,
            'swing_mode': swing_mode
        }

    async def async_get_homes(self):
        """Get all the homes of the account"""
        endpoint = "%s/1.0/HomeCloudService.svc/EnumHomes" % self.base_url
        resp = await self._async_request(endpoint)
        return (await resp.json())['EnumHomesResult']['Homes']

    async def async_get_devices(self, home_id):
        """Get all the devices of a home"""
        data = await self._async_get_data_packets(home_id)
        devices = self._parse_devices(data)
        return devices

    async def async_get_status(self, home_id, device_id):
        """Get the status of a device"""
        return (await self.async_get_devices(home_id))[device_id]

    async def _async_set_device_mode(self, device_id, mode):
        mode['endpointID'] = device_id
        endpoint = "%s/1.0/HomeCloudCommandService.svc/HVACSetModes" % self.base_url
        return await self._async_request(endpoint, mode)

    async def _async_send_command(self, device_id, command):
        endpoint = "%s/1.0/HomeCloudCommandService.svc/HVACSendCommand" % self.base_url
        command_config = {
            "endpointID": device_id,
            "subCommand": command
        }
        return await self._async_request(endpoint, command_config)

    async def async_set_mode(self, device_id, mode, temp, fan='auto', swing_mode='off', preset_mode='none'):
        """Set the mode of a device"""
        config = {
            'desiredTempC': str(temp),
            'fanMode': FAN_MODE[fan],
            'flags': 255,
            'mode': MODE[mode]
        }
        response = await self._async_set_device_mode(device_id, config)
        LOGGER.debug("preset_mode = %s, swing_mode = %s", preset_mode, swing_mode)
        if preset_mode != 'none' or swing_mode != 'off':
            command = PRESET_MODE.get(preset_mode) | SWING_MODE.get(swing_mode)
            LOGGER.debug("command = %d", command)
            await self._async_send_command(device_id, command)
        return response
