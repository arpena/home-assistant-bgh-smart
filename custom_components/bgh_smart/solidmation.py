"""BGH Smart devices API client"""
import requests

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
    'on': 0x51
}

PRESET_MODE = {
    'none': 0,
    'boost': 0x71
}


class SolidmationClient:
    """BGH client implementation"""

    def __init__(self, email, password, backend="myhabeetat"):
        base_url = BASE_URL[backend]
        self.token = self._login(email, password, base_url)
        self.api_url = "%s/1.0" % base_url

    @staticmethod
    def _login(email, password, base_url):
        endpoint = "%s/control/LoginPage.aspx/DoStandardLogin" % base_url
        resp = requests.post(endpoint, json={'user': email, 'password': password})
        return resp.json()['d']

    def _request(self, endpoint, payload=None):
        if payload is None:
            payload = {}
        payload['token'] = {'Token': self.token}
        return requests.post(endpoint, json=payload, timeout=10)

    def _get_data_packets(self, home_id):
        endpoint = "%s/HomeCloudService.svc/GetDataPacket" % self.api_url
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
        resp = self._request(endpoint, payload)
        return resp.json()['GetDataPacketResult']

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

            devices[device['device_id']] = device

        return devices

    @staticmethod
    def _parse_raw_data(data):
        if data is None:
            return {}

        temperature = next(item['Value'] for item in data if item['ValueType'] == 13)
        if temperature:
            temperature = float(temperature)
            if temperature <= -50:
                temperature = None

        target_temperature = next(item['Value'] for item in data if item['ValueType'] == 20)
        if target_temperature:
            target_temperature = float(target_temperature)
            if target_temperature == 255:
                target_temperature = 20

        fan_speed = next(item['Value'] for item in data if item['ValueType'] == 15)
        if fan_speed:
            fan_speed = int(fan_speed)

        mode_id = next(item['Value'] for item in data if item['ValueType'] == 14)
        if mode_id:
            mode_id = int(mode_id)

        swing_mode = next(item['Value'] for item in data if item['ValueType'] == 18)
        if swing_mode:
            swing_mode = int(swing_mode)

        # preset_mode = next(item['Value'] for item in data if item['ValueType'] == 18)
        # if preset_mode:
        #     preset_mode = int(preset_mode)
        return {
            'temperature': temperature,
            'target_temperature': target_temperature,
            'fan_speed': fan_speed,
            'mode_id': mode_id,
            'swing_mode': swing_mode
        }

    def get_homes(self):
        """Get all the homes of the account"""
        endpoint = "%s/HomeCloudService.svc/EnumHomes" % self.api_url
        resp = self._request(endpoint)
        return resp.json()['EnumHomesResult']['Homes']

    def get_devices(self, home_id):
        """Get all the devices of a home"""
        data = self._get_data_packets(home_id)
        devices = self._parse_devices(data)
        return devices

    def get_status(self, home_id, device_id):
        """Get the status of a device"""
        return self.get_devices(home_id)[device_id]

    def _set_device_mode(self, device_id, mode):
        mode['endpointID'] = device_id
        endpoint = "%s/HomeCloudCommandService.svc/HVACSetModes" % self.api_url
        return self._request(endpoint, mode)

    def _send_command(self, device_id, command):
        endpoint = "%s/HomeCloudCommandService.svc/HVACSendCommand" % self.api_url
        command_config = {
            "endpointID": device_id,
            "subCommand": command
        }
        return self._request(endpoint, command_config)

    def set_mode(self, device_id, mode, temp, fan='auto', swing_mode='off', preset_mode='none'):
        """Set the mode of a device"""
        config = {
            'desiredTempC': str(temp),
            'fanMode': FAN_MODE[fan],
            'flags': 255,
            'mode': MODE[mode]
        }
        response = self._set_device_mode(device_id, config)
        command = PRESET_MODE.get(preset_mode) or SWING_MODE.get(swing_mode)
        self._send_command(device_id, command)
        return response
