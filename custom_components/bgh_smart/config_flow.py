"""Config flow for BGH Smart integration."""

from aiohttp import ClientError
from homeassistant import config_entries
from homeassistant.const import (
    CONF_PASSWORD,
    CONF_USERNAME,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from . import solidmation
import voluptuous as vol

from .const import DOMAIN, LOGGER, INTEGRATION_NAME, CONF_BACKEND, BACKEND_BGH, BACKEND_MYHABEETAT
from .options_flow import OptionsFlow


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for BGH Smart."""

    VERSION = 1
    MINOR_VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    _username: str | None = None
    _backend: str | None = None

    async def async_validate_input(self, user_input):
        """Validate user credentials."""
        self._username = user_input.get(CONF_USERNAME) or ""
        password = user_input.get(CONF_PASSWORD) or ""
        self._backend = user_input.get(CONF_BACKEND) or ""

        session = async_get_clientsession(self.hass)

        client = solidmation.SolidmationClient(username=self._username, password=password, backend=self._backend, websession=session)

        homes = await client.async_get_homes()

        # Verify that passed in configuration works
        if not homes:
            LOGGER.error("Could not connect to BGH Smart cloud")
            return

        return self.async_create_entry(
            title=INTEGRATION_NAME,
            data=user_input,
        )

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        if user_input:
#            await self.async_set_unique_id(user_input.get(CONF_HOST))
            self._abort_if_unique_id_configured()

            try:
                return await self.async_validate_input(user_input)
            except solidmation.AuthenticationException:
                errors["base"] = "invalid_auth"
            except (TimeoutError, ClientError, ConnectionError):
                errors["base"] = "cannot_connect"
            except solidmation.LoginTimeoutException:
                errors["base"] = "login_timeout"
            except solidmation.LoginRetryErrorException:
                errors["base"] = "login_retry_error"
            except solidmation.UnsupportedHostException:
                errors["base"] = "unsupported_host"
            except Exception as exception:  # pylint: disable=broad-except
                errors["base"] = "unknown"
                LOGGER.exception(exception)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME): str,
                    vol.Required(CONF_PASSWORD): str,
                    vol.Optional(CONF_BACKEND, default=BACKEND_BGH): vol.In(
        [BACKEND_BGH, BACKEND_MYHABEETAT])
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get options flow for this handler."""
        return OptionsFlow(config_entry)