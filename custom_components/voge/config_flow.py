"""Config flow for VOGE account authentication and setup."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import VogeApiError, VogeAuthError, VogeModernClient
from .auth_manager import VogeAuthClient
from .const import (
    AUTH_MODE_PASSWORD,
    AUTH_MODE_TOKEN,
    CONF_ACCOUNT_KEY,
    CONF_ALERT_INTERVAL,
    CONF_AUTH_MODE,
    CONF_CONVERT_COORDINATES,
    CONF_DEVICE_ID,
    CONF_ENABLE_ALERTS,
    CONF_MOBILE,
    CONF_PASSWORD,
    CONF_PRODUCT_ID,
    CONF_PRODUCT_NAME,
    CONF_SCAN_INTERVAL,
    CONF_SERVER_TIMEZONE,
    CONF_STATS_INTERVAL,
    CONF_TOKEN,
    DEFAULT_ALERT_INTERVAL,
    DEFAULT_CONVERT_COORDINATES,
    DEFAULT_ENABLE_ALERTS,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SERVER_TIMEZONE,
    DEFAULT_STATS_INTERVAL,
    DOMAIN,
    MAX_ALERT_INTERVAL,
    MAX_SCAN_INTERVAL,
    MAX_STATS_INTERVAL,
    MIN_ALERT_INTERVAL,
    MIN_SCAN_INTERVAL,
    MIN_STATS_INTERVAL,
)
from .models import VehicleSnapshot, parse_vehicle_list
from .util import stable_hash


@dataclass(slots=True)
class _PendingSetup:
    auth_mode: str
    token: str
    mobile: str | None
    password: str | None
    vehicles: list[VehicleSnapshot]


async def _validate_token(hass: Any, token: str) -> list[VehicleSnapshot]:
    """Validate an existing token using the read-only vehicle list endpoint."""
    client = VogeModernClient(async_get_clientsession(hass), token)
    vehicles = parse_vehicle_list(await client.get_devices())
    if not vehicles:
        raise VogeApiError("modern.devices", "no_bound_vehicles")
    return vehicles


async def _validate_credentials(
    hass: Any,
    mobile: str,
    password: str,
) -> tuple[str, list[VehicleSnapshot]]:
    """Log in, then validate the returned token with a read-only GET."""
    token = await VogeAuthClient(async_get_clientsession(hass)).login(mobile, password)
    vehicles = await _validate_token(hass, token)
    return token, vehicles


def _vehicle_label(vehicle: VehicleSnapshot, ordinal: int) -> str:
    return f"{vehicle.display_name()} #{ordinal}"


class VogeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Configure one VOGE cloud account."""

    VERSION = 2

    def __init__(self) -> None:
        self._pending: _PendingSetup | None = None
        self._auth_mode: str = AUTH_MODE_PASSWORD
        self._reauth_entry: ConfigEntry | None = None

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Choose password login by default, with token-only compatibility."""
        errors: dict[str, str] = {}
        if user_input is not None:
            # Keep programmatic setup of the original token-only flow compatible.
            if CONF_TOKEN in user_input and CONF_AUTH_MODE not in user_input:
                self._auth_mode = AUTH_MODE_TOKEN
            else:
                self._auth_mode = user_input.get(CONF_AUTH_MODE, AUTH_MODE_PASSWORD)
                if self._auth_mode not in {AUTH_MODE_PASSWORD, AUTH_MODE_TOKEN}:
                    errors["base"] = "invalid_auth_mode"
                else:
                    return await self.async_step_credentials()
            if not errors:
                return await self._handle_credentials(user_input)

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_AUTH_MODE,
                    default=AUTH_MODE_PASSWORD,
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            SelectOptionDict(
                                value=AUTH_MODE_PASSWORD,
                                label="VOGE account password",
                            ),
                            SelectOptionDict(
                                value=AUTH_MODE_TOKEN,
                                label="Existing access token (advanced)",
                            ),
                        ],
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                )
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_credentials(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Collect credentials only through the local HA form."""
        errors: dict[str, str] = {}
        if user_input is not None:
            return await self._handle_credentials(user_input, errors)
        return self.async_show_form(
            step_id="credentials",
            data_schema=self._credentials_schema(self._auth_mode),
            errors=errors,
        )

    async def _handle_credentials(
        self,
        user_input: dict[str, Any],
        errors: dict[str, str] | None = None,
    ) -> ConfigFlowResult:
        errors = errors if errors is not None else {}
        try:
            if self._auth_mode == AUTH_MODE_PASSWORD:
                mobile = user_input[CONF_MOBILE].strip()
                password = user_input[CONF_PASSWORD]
                token, vehicles = await _validate_credentials(self.hass, mobile, password)
                pending = _PendingSetup(
                    AUTH_MODE_PASSWORD,
                    token,
                    mobile,
                    password,
                    vehicles,
                )
            else:
                token = user_input[CONF_TOKEN].strip()
                vehicles = await _validate_token(self.hass, token)
                pending = _PendingSetup(AUTH_MODE_TOKEN, token, None, None, vehicles)
        except VogeAuthError:
            errors["base"] = "invalid_auth"
        except VogeApiError:
            errors["base"] = "cannot_connect"
        except (KeyError, TypeError, ValueError):
            errors["base"] = "invalid_auth"
        except Exception:
            errors["base"] = "unknown"
        else:
            self._pending = pending
            if len(vehicles) == 1:
                return await self._create_entry(vehicles[0])
            return await self.async_step_vehicle()
        return self.async_show_form(
            step_id="credentials",
            data_schema=self._credentials_schema(self._auth_mode),
            errors=errors,
        )

    @staticmethod
    def _credentials_schema(auth_mode: str) -> vol.Schema:
        if auth_mode == AUTH_MODE_TOKEN:
            return vol.Schema(
                {
                    vol.Required(CONF_TOKEN): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    )
                }
            )
        return vol.Schema(
            {
                vol.Required(CONF_MOBILE): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.TEXT)
                ),
                vol.Required(CONF_PASSWORD): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                ),
            }
        )

    async def async_step_vehicle(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Select locally without changing the server-side default vehicle."""
        if self._pending is None:
            return self.async_abort(reason="setup_state_missing")

        vehicles_by_id = {vehicle.device_id: vehicle for vehicle in self._pending.vehicles}
        if user_input is not None:
            vehicle = vehicles_by_id.get(user_input[CONF_DEVICE_ID])
            if vehicle is None:
                return self.async_show_form(
                    step_id="vehicle",
                    data_schema=self._vehicle_schema(self._pending.vehicles),
                    errors={"base": "vehicle_missing"},
                )
            return await self._create_entry(vehicle)

        return self.async_show_form(
            step_id="vehicle",
            data_schema=self._vehicle_schema(self._pending.vehicles),
        )

    def _vehicle_schema(self, vehicles: list[VehicleSnapshot]) -> vol.Schema:
        options = [
            SelectOptionDict(value=vehicle.device_id, label=_vehicle_label(vehicle, index))
            for index, vehicle in enumerate(vehicles, start=1)
        ]
        return vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): SelectSelector(
                    SelectSelectorConfig(
                        options=options,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                )
            }
        )

    async def _create_entry(self, vehicle: VehicleSnapshot) -> ConfigFlowResult:
        if self._pending is None:
            return self.async_abort(reason="setup_state_missing")

        account_source = vehicle.user_id or vehicle.user_no or vehicle.device_id
        account_key = stable_hash(account_source)
        await self.async_set_unique_id(f"account_{account_key}")
        self._abort_if_unique_id_configured()

        product_name = vehicle.display_name()
        data: dict[str, Any] = {
            CONF_AUTH_MODE: self._pending.auth_mode,
            CONF_TOKEN: self._pending.token,
            CONF_DEVICE_ID: vehicle.device_id,
            CONF_PRODUCT_NAME: product_name,
            CONF_ACCOUNT_KEY: account_key,
        }
        if vehicle.product_id is not None:
            data[CONF_PRODUCT_ID] = vehicle.product_id
        if self._pending.auth_mode == AUTH_MODE_PASSWORD:
            data[CONF_MOBILE] = self._pending.mobile
            data[CONF_PASSWORD] = self._pending.password
        return self.async_create_entry(
            title=product_name,
            data=data,
            options={
                CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
                CONF_STATS_INTERVAL: DEFAULT_STATS_INTERVAL,
                CONF_ALERT_INTERVAL: DEFAULT_ALERT_INTERVAL,
                CONF_SERVER_TIMEZONE: DEFAULT_SERVER_TIMEZONE,
                CONF_CONVERT_COORDINATES: DEFAULT_CONVERT_COORDINATES,
                CONF_ENABLE_ALERTS: DEFAULT_ENABLE_ALERTS,
            },
        )

    async def async_step_reauth(
        self,
        entry_data: dict[str, Any],
    ) -> ConfigFlowResult:
        """Start credential replacement without changing the selected motorcycle."""
        entry_id = self.context.get("entry_id")
        self._reauth_entry = (
            self.hass.config_entries.async_get_entry(entry_id)
            if isinstance(entry_id, str)
            else None
        )
        if self._reauth_entry is not None:
            mode = self._reauth_entry.data.get(CONF_AUTH_MODE)
            self._auth_mode = (
                mode
                if mode in {AUTH_MODE_PASSWORD, AUTH_MODE_TOKEN}
                else AUTH_MODE_TOKEN
            )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Validate replacement credentials against the existing device ID."""
        if self._reauth_entry is None:
            return self.async_abort(reason="reauth_entry_missing")

        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                if self._auth_mode == AUTH_MODE_PASSWORD:
                    mobile = user_input[CONF_MOBILE].strip()
                    password = user_input[CONF_PASSWORD]
                    token, vehicles = await _validate_credentials(self.hass, mobile, password)
                    updates = {
                        CONF_AUTH_MODE: AUTH_MODE_PASSWORD,
                        CONF_MOBILE: mobile,
                        CONF_PASSWORD: password,
                        CONF_TOKEN: token,
                    }
                else:
                    token = user_input[CONF_TOKEN].strip()
                    vehicles = await _validate_token(self.hass, token)
                    updates = {CONF_AUTH_MODE: AUTH_MODE_TOKEN, CONF_TOKEN: token}
            except VogeAuthError:
                errors["base"] = "invalid_auth"
            except VogeApiError:
                errors["base"] = "cannot_connect"
            except (KeyError, TypeError, ValueError):
                errors["base"] = "invalid_auth"
            except Exception:
                errors["base"] = "unknown"
            else:
                selected = next(
                    (
                        vehicle
                        for vehicle in vehicles
                        if vehicle.device_id == self._reauth_entry.data[CONF_DEVICE_ID]
                    ),
                    None,
                )
                if selected is None:
                    errors["base"] = "target_vehicle_missing"
                else:
                    return self.async_update_reload_and_abort(
                        self._reauth_entry,
                        data_updates=updates,
                        reason="reauth_successful",
                    )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=self._credentials_schema(self._auth_mode),
            errors=errors,
        )

    @staticmethod
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the polling and coordinate options flow."""
        return VogeOptionsFlow()


class VogeOptionsFlow(OptionsFlow):
    """Configure conservative polling and timestamp assumptions."""

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Update options and reload the entry."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                ZoneInfo(user_input[CONF_SERVER_TIMEZONE])
            except ZoneInfoNotFoundError:
                errors[CONF_SERVER_TIMEZONE] = "invalid_timezone"
            else:
                return self.async_create_entry(title="", data=user_input)

        options = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): vol.All(vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL)),
                vol.Required(
                    CONF_STATS_INTERVAL,
                    default=options.get(CONF_STATS_INTERVAL, DEFAULT_STATS_INTERVAL),
                ): vol.All(vol.Coerce(int), vol.Range(min=MIN_STATS_INTERVAL, max=MAX_STATS_INTERVAL)),
                vol.Required(
                    CONF_ALERT_INTERVAL,
                    default=options.get(CONF_ALERT_INTERVAL, DEFAULT_ALERT_INTERVAL),
                ): vol.All(vol.Coerce(int), vol.Range(min=MIN_ALERT_INTERVAL, max=MAX_ALERT_INTERVAL)),
                vol.Required(
                    CONF_SERVER_TIMEZONE,
                    default=options.get(CONF_SERVER_TIMEZONE, DEFAULT_SERVER_TIMEZONE),
                ): str,
                vol.Required(
                    CONF_CONVERT_COORDINATES,
                    default=options.get(CONF_CONVERT_COORDINATES, DEFAULT_CONVERT_COORDINATES),
                ): bool,
                vol.Required(
                    CONF_ENABLE_ALERTS,
                    default=options.get(CONF_ENABLE_ALERTS, DEFAULT_ENABLE_ALERTS),
                ): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
