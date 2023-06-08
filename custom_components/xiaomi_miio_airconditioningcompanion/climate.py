"""
Support for Xiaomi Air Conditioner Companion (AC Partner)
"""
import asyncio
import enum
import logging
import time
from datetime import timedelta
from functools import partial
import voluptuous as vol

import homeassistant.helpers.config_validation as cv
from homeassistant import config_entries
from homeassistant.core import callback, HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.event import async_track_state_change
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util.dt import utcnow
from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    ATTR_HVAC_MODE,
    HVAC_MODE_AUTO,
    HVAC_MODE_COOL,
    HVAC_MODE_DRY,
    HVAC_MODE_FAN_ONLY,
    HVAC_MODE_HEAT,
    HVAC_MODE_OFF,
    SUPPORT_FAN_MODE,
    SUPPORT_SWING_MODE,
    SUPPORT_TARGET_TEMPERATURE
)
from homeassistant.components.remote import (
    ATTR_DELAY_SECS,
    ATTR_NUM_REPEATS,
    DEFAULT_DELAY_SECS,
    DEFAULT_NUM_REPEATS,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_TEMPERATURE,
    CONF_HOST,
    CONF_MAC,
    CONF_TIMEOUT,
    STATE_ON,
    STATE_OFF,
    STATE_UNKNOWN,
    STATE_UNAVAILABLE,
    PRECISION_WHOLE
)

from miio import DeviceException
from miio.airconditioningcompanion import (
    FanSpeed,
    Led,
    Power,
    SwingMode
)
from miio.airconditioningcompanion import OperationMode as MiioOperationMode

from .const import (
    ATTR_AIR_CONDITION_MODEL,
    ATTR_SWING_MODE,
    ATTR_FAN_MODE,
    ATTR_LOAD_POWER,
    ATTR_LED,
    CONF_COMMAND,
    CONF_MODEL,
    CONF_HUMIDITY_SENSOR,
    CONF_TEMPERATURE_SENSOR,
    CONF_POWER_SENSOR,
    CONF_MAX_TEMP,
    CONF_MIN_TEMP,
    CONF_SLOT,
    DATA_KEY,
    DEFAULT_DELAY,
    DEFAULT_TARGET_TEMPERATURE,
    DEFAULT_TIMEOUT,
    DEFAULT_SLOT,
    DOMAIN,
    MODELS_MIIO,
    TARGET_TEMPERATURE_STEP,
    ACPARTNER_PROPS
)

SUPPORT_FLAGS = (
    SUPPORT_TARGET_TEMPERATURE |
    SUPPORT_FAN_MODE |
    SUPPORT_SWING_MODE
)


SERVICE_LEARN_COMMAND = "climate_learn_command"
SERVICE_SEND_COMMAND = "climate_send_command"

SERVICE_SCHEMA = vol.Schema({vol.Required(ATTR_ENTITY_ID): cv.entity_ids})

SERVICE_SCHEMA_LEARN_COMMAND = SERVICE_SCHEMA.extend(
    {
        vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): vol.All(
            int, vol.Range(min=0)
        ),
        vol.Optional(CONF_SLOT, default=DEFAULT_SLOT): vol.All(
            int, vol.Range(min=2, max=1000000)
        ),
    }
)

SERVICE_SCHEMA_SEND_COMMAND = SERVICE_SCHEMA.extend(
    {
        vol.Required(CONF_COMMAND, default=""): cv.string,
        vol.Optional(ATTR_NUM_REPEATS, default=DEFAULT_NUM_REPEATS): cv.positive_int,
        vol.Optional(ATTR_DELAY_SECS, default=DEFAULT_DELAY_SECS): vol.Coerce(float),
    }
)

SERVICE_TO_METHOD = {
    SERVICE_LEARN_COMMAND: {
        "method": "async_learn_command",
        "schema": SERVICE_SCHEMA_LEARN_COMMAND,
    },
    SERVICE_SEND_COMMAND: {
        "method": "async_send_command",
        "schema": SERVICE_SCHEMA_SEND_COMMAND,
    },
}

_LOGGER = logging.getLogger(__name__)

class OperationMode(enum.Enum):
    Heat = HVAC_MODE_HEAT
    Cool = HVAC_MODE_COOL
    Auto = HVAC_MODE_AUTO
    Dehumidify = HVAC_MODE_DRY
    Ventilate = HVAC_MODE_FAN_ONLY
    Off = HVAC_MODE_OFF

async def async_setup_entry(
    hass: HomeAssistant,
    entry: config_entries.ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Xiaomi Air Conditioning Companion platform."""

    host = entry.options[CONF_HOST]
    model = entry.options[CONF_MODEL]
    name = entry.title
    unique_id = entry.unique_id

    acpartner = hass.data[DOMAIN][host]

    try:
        entities = []

        if model in MODELS_MIIO:
            air_conditioning_companion = XiaomiACPartnerClimate(hass, entry.options, name, unique_id, acpartner)
            entities.extend(
                [air_conditioning_companion]
            )
            hass.data[DATA_KEY][host] = air_conditioning_companion

        async_add_entities(entities)
    except AttributeError as ex:
        _LOGGER.error(ex)


    async def async_service_handler(service):
        """Map services to methods on XiaomiAirConditioningCompanion."""
        method = SERVICE_TO_METHOD.get(service.service)
        params = {
            key: value for key, value in service.data.items() if key != ATTR_ENTITY_ID
        }
        entity_ids = service.data.get(ATTR_ENTITY_ID)
        if entity_ids:
            devices = [
                device
                for device in hass.data[DATA_KEY].values()
                if device.entity_id in entity_ids
            ]
        else:
            devices = hass.data[DATA_KEY].values()

        update_tasks = []
        for device in devices:
            if not hasattr(device, method["method"]):
                continue
            await getattr(device, method["method"])(**params)
            await device.async_update_ha_state(True)

    for service in SERVICE_TO_METHOD:
        schema = SERVICE_TO_METHOD[service].get("schema", SERVICE_SCHEMA)
        hass.services.async_register(
            DOMAIN, service, async_service_handler, schema=schema
        )


class XiaomiACPartnerClimate(ClimateEntity, RestoreEntity):
    """Implementation of a Xiaomi Air Conditioning Companion sensor."""

    def __init__(self, hass, config, name, unique_id, acpartner):
        self.hass = hass
        self._acpartner = acpartner
        self._unique_id = unique_id
        self._name = name
        self._model = config.get(CONF_MODEL)
        self._mac = config.get(CONF_MAC, None)
        self._slot = None
        self._delay = DEFAULT_DELAY
        self._temperature_sensor = config.get(CONF_TEMPERATURE_SENSOR)
        self._humidity_sensor = config.get(CONF_HUMIDITY_SENSOR)
        self._power_sensor = config.get(CONF_POWER_SENSOR)
      #  self._power_sensor_restore_state = config.get(CONF_POWER_SENSOR_RESTORE_STATE)
        self._power_sensor_restore_state = False
        self._air_condition_model = None

        self._available = False
        self._state = None
        self._state_attrs = {
            ATTR_AIR_CONDITION_MODEL: None,
            ATTR_LOAD_POWER: None,
            ATTR_TEMPERATURE: None,
            ATTR_SWING_MODE: None,
            ATTR_HVAC_MODE: None,
            ATTR_LED: None,
        }

        self._min_temperature = config.get(CONF_MIN_TEMP, 16)
        self._max_temperature = config.get(CONF_MAX_TEMP, 32)
        self._precision = TARGET_TEMPERATURE_STEP

        self._operation_modes = [mode.value for mode in OperationMode]
        self._fan_modes =  [speed.name.lower() for speed in FanSpeed]
        self._swing_modes = [mode.name.lower() for mode in SwingMode if "Unknown" not in mode.name]
        self._commands = []

        self._target_temperature = DEFAULT_TARGET_TEMPERATURE
        self._hvac_mode = HVAC_MODE_OFF
        self._current_fan_mode = self._fan_modes[0]
        self._current_swing_mode = None
        self._last_on_operation = None

        self._current_temperature = None
        self._current_humidity = None

        self._unit = hass.config.units.temperature_unit

        # Supported features
        self._support_flags = SUPPORT_FLAGS
        self._support_swing = False

        if self._swing_modes:
            self._support_flags = self._support_flags | SUPPORT_SWING_MODE
            self._current_swing_mode = self._swing_modes[0]
            self._support_swing = True

        self._temp_lock = asyncio.Lock()
        self._on_by_remote = False

        self._attr_unique_id = self._unique_id

    async def async_added_to_hass(self):
        """Run when entity about to be added."""
        await super().async_added_to_hass()

        last_state = await self.async_get_last_state()

        if last_state is not None:
            self._hvac_mode = last_state.state
            self._current_fan_mode = last_state.attributes['fan_mode']
            self._current_swing_mode = last_state.attributes.get('swing_mode')
            self._target_temperature = last_state.attributes['temperature'] if last_state.attributes['temperature'] else DEFAULT_TARGET_TEMPERATURE

            if 'last_on_operation' in last_state.attributes:
                self._last_on_operation = last_state.attributes['last_on_operation']
                self._state = self._last_on_operation

        if self._temperature_sensor:
            async_track_state_change(self.hass, self._temperature_sensor,
                                        self._async_temp_sensor_changed)

            temp_sensor_state = self.hass.states.get(self._temperature_sensor)
            if temp_sensor_state and temp_sensor_state.state != STATE_UNKNOWN:
                self._async_update_temp(temp_sensor_state)

        if self._humidity_sensor:
            async_track_state_change(self.hass, self._humidity_sensor,
                                        self._async_humidity_sensor_changed)

            humidity_sensor_state = self.hass.states.get(self._humidity_sensor)
            if humidity_sensor_state and humidity_sensor_state.state != STATE_UNKNOWN:
                self._async_update_humidity(humidity_sensor_state)

        if self._power_sensor:
            async_track_state_change(self.hass, self._power_sensor,
                                     self._async_power_sensor_changed)

    @property
    def unique_id(self):
        """Return a unique ID."""
        return self._unique_id

    @property
    def name(self):
        """Return the name of the climate device."""
        return self._name

    @property
    def state(self):
        """Return the current state."""
        if self.hvac_mode != HVAC_MODE_OFF:
            return self.hvac_mode
        return HVAC_MODE_OFF

    @property
    def temperature_unit(self):
        """Return the unit of measurement."""
        return self._unit

    @property
    def min_temp(self):
        """Return the polling state."""
        return self._min_temperature

    @property
    def max_temp(self):
        """Return the polling state."""
        return self._max_temperature

    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        return self._target_temperature

    @property
    def target_temperature_step(self):
        """Return the supported step of target temperature."""
        return self._precision

    @property
    def hvac_modes(self):
        """Return the list of available operation modes."""
        return self._operation_modes

    @property
    def hvac_mode(self):
        """Return hvac mode ie. heat, cool."""
        return self._hvac_mode

    @property
    def last_on_operation(self):
        """Return the last non-idle operation ie. heat, cool."""
        return self._last_on_operation

    @property
    def fan_modes(self):
        """Return the list of available fan modes."""
        return self._fan_modes

    @property
    def fan_mode(self):
        """Return the fan setting."""
        return self._current_fan_mode

    @property
    def swing_modes(self):
        """Return the swing modes currently supported for this device."""
        return self._swing_modes

    @property
    def swing_mode(self):
        """Return the current swing mode."""
        return self._current_swing_mode

    @property
    def current_temperature(self):
        """Return the current temperature."""
        return self._current_temperature

    @property
    def current_humidity(self):
        """Return the current humidity."""
        return self._current_humidity

    @property
    def supported_features(self):
        """Return the list of supported features."""
        return self._support_flags

    @property
    def extra_state_attributes(self):
        """Platform specific attributes."""
        return {
            'last_on_operation': self._last_on_operation,
            'data': self._slot,
        }

    @property
    def device_info(self):
        """Return the device info."""
        info = self._acpartner.info()
        device_info = {
            "identifiers": {(DOMAIN, self._unique_id)},
            "manufacturer": (self._model or "Xiaomi").split(".", 1)[0].capitalize(),
            "name": self._name,
            "model": self._model,
            "sw_version": info.firmware_version,
            "hw_version": info.hardware_version
        }

        if self._mac is not None:
            device_info["connections"] = {(dr.CONNECTION_NETWORK_MAC, self._mac)}

        return device_info


    async def _send_configuration(self):
        if self._air_condition_model is not None:
            try:
                await self._try_command(
                    "Sending new air conditioner configuration failed.",
                    self._acpartner.send_configuration,
                    self._air_condition_model,
                    Power(int(self._state)),
                    MiioOperationMode[OperationMode(self._hvac_mode).name]
                        if self._state else MiioOperationMode[OperationMode(self._last_on_operation).name],
                    self._target_temperature if isinstance(
                        self._target_temperature, int) else int(self._target_temperature),
                    FanSpeed[self._current_fan_mode.capitalize()],
                    SwingMode[self._current_swing_mode.capitalize()],
                    Led.Off,
                )
            except ValueError:
                _LOGGER.error(
                    "send configuration with invalid value"
                )
        else:
            _LOGGER.error(
                "Model number of the air condition unknown. "
                "Configuration cannot be sent."
            )

    async def async_set_temperature(self, **kwargs):
        """Set new target temperatures."""
        hvac_mode = kwargs.get(ATTR_HVAC_MODE)
        temperature = kwargs.get(ATTR_TEMPERATURE)

        if temperature is None:
            return

        if temperature < self._min_temperature or temperature > self._max_temperature:
            _LOGGER.warning('The temperature value is out of min/max range')
            return

        if self._precision == PRECISION_WHOLE:
            self._target_temperature = round(temperature)
        else:
            self._target_temperature = round(temperature, 1)

        if hvac_mode:
            await self.async_set_hvac_mode(hvac_mode)
            return

        if not self._hvac_mode.lower() == HVAC_MODE_OFF:
            await self._send_configuration()

        self.async_write_ha_state()

    async def async_set_hvac_mode(self, hvac_mode):
        """Set operation mode."""
        self._hvac_mode = hvac_mode

        if hvac_mode == OperationMode.Off.value:
            result = await self._try_command(
                "Turning the miio device off failed.", self._acpartner.off
            )
            if result:
                self._state = False
                self._hvac_mode = HVAC_MODE_OFF
                await self._send_configuration()
        else:
            self._state = True
            await self._send_configuration()

        self.async_write_ha_state()

    async def async_set_fan_mode(self, fan_mode):
        """Set fan mode."""
        self._current_fan_mode = fan_mode

        if not self._hvac_mode.lower() == HVAC_MODE_OFF:
            await self._try_command("Turning the acpartner on failed.", self._acpartner.off)

        self.async_write_ha_state()

    async def async_set_swing_mode(self, swing_mode):
        """Set swing mode."""
        self._current_swing_mode = swing_mode

        if not self._hvac_mode.lower() == HVAC_MODE_OFF:
            await self._try_command("Turning the acpartner on failed.", self._acpartner.on)
        self.async_write_ha_state()

    async def async_turn_off(self):
        """Turn off."""
        self._state = False
        await self.async_set_hvac_mode(HVAC_MODE_OFF)

    async def async_turn_on(self):
        """Turn on."""
        if self._last_on_operation is not None:
            await self.async_set_hvac_mode(self._last_on_operation)
        else:
            await self.async_set_hvac_mode(self._operation_modes[1])
        self._state = True

    async def _try_command(self, mask_error, func, *args, **kwargs):
        """Call a plug command handling error messages."""
        try:
            result = await self.hass.async_add_executor_job(
                partial(func, *args, **kwargs)
            )

            _LOGGER.debug("Response received from climate: %s", result)

            return True if "ok" in result else False
        except DeviceException as exc:
            if self._available:
                _LOGGER.error(mask_error, exc)
                self._available = False

            return False

    async def async_update(self):
        """Fetch state from the device."""
        state = None
        try:
            state = await self.hass.async_add_executor_job(self._acpartner.status)
            _LOGGER.debug("Got new state: %s", state)

        except DeviceException as ex:
            if self._available:
                self._available = False
                _LOGGER.debug("Got exception while fetching the state: %s", ex)

        self._available = True
        if state:
            self._state_attrs.update(
                {
                    ATTR_AIR_CONDITION_MODEL: state.air_condition_model.hex(),
                    ATTR_LOAD_POWER: state.load_power,
                    ATTR_TEMPERATURE: state.target_temperature,
                    ATTR_SWING_MODE: state.swing_mode.name.lower(),
                    ATTR_FAN_MODE: state.fan_speed.name.lower(),
                    ATTR_HVAC_MODE: state.mode.name.lower() if self._state else "off",
                    ATTR_LED: state.led,
                }
            )
        self._last_on_operation = OperationMode[state.mode.name].value
        if state and state.power == "off":
            self._hvac_mode = HVAC_MODE_OFF
            self._state = False
        else:
            self._hvac_mode = self._last_on_operation
            self._state = True
        if self._air_condition_model is None and state:
            self._air_condition_model = state.air_condition_model.hex()


    async def _async_temp_sensor_changed(self, entity_id, old_state, new_state):
        """Handle temperature sensor changes."""
        if new_state is None:
            return

        self._async_update_temp(new_state)
        self.async_write_ha_state()

    async def _async_humidity_sensor_changed(self, entity_id, old_state, new_state):
        """Handle humidity sensor changes."""
        if new_state is None:
            return

        self._async_update_humidity(new_state)
        self.async_write_ha_state()

    async def _async_power_sensor_changed(self, entity_id, old_state, new_state):
        """Handle power sensor changes."""
        if new_state is None:
            return

        if old_state is not None and new_state.state == old_state.state:
            return

        if new_state.state == STATE_ON and self._hvac_mode == HVAC_MODE_OFF:
            self._on_by_remote = True
            if self._power_sensor_restore_state == True and self._last_on_operation is not None:
                self._hvac_mode = self._last_on_operation
            else:
                self._hvac_mode = STATE_ON

            self.async_write_ha_state()

        if new_state.state == STATE_OFF:
            self._on_by_remote = False
            if self._hvac_mode != HVAC_MODE_OFF:
                self._hvac_mode = HVAC_MODE_OFF
            self.async_write_ha_state()

    @callback
    def _async_update_temp(self, state):
        """Update thermostat with latest state from temperature sensor."""
        try:
            if state.state != STATE_UNKNOWN and state.state != STATE_UNAVAILABLE:
                self._current_temperature = float(state.state)
        except ValueError as ex:
            _LOGGER.error("Unable to update from temperature sensor: %s", ex)

    @callback
    def _async_update_humidity(self, state):
        """Update thermostat with latest state from humidity sensor."""
        try:
            if state.state != STATE_UNKNOWN and state.state != STATE_UNAVAILABLE:
                self._current_humidity = float(state.state)
        except ValueError as ex:
            _LOGGER.error("Unable to update from humidity sensor: %s", ex)

    async def async_learn_command(self, slot, timeout):
        """Learn a infrared command."""
        await self.hass.async_add_job(self._acpartner.learn, slot)

        _LOGGER.info("Press the key you want Home Assistant to learn")
        start_time = utcnow()
        while (utcnow() - start_time) < timedelta(seconds=timeout):
            message = await self.hass.async_add_job(self._acpartner.learn_result)
            # FIXME: Improve python-miio here?
            message = message[0]
            _LOGGER.debug("Message received from device: '%s'", message)
            if message.startswith("FE"):
                log_msg = "Received command is: {}".format(message)
                _LOGGER.info(log_msg)
                self.hass.components.persistent_notification.async_create(
                    log_msg, title="Xiaomi Miio Remote"
                )
                await self.hass.async_add_job(self._acpartner.learn_stop, slot)
                return

            await asyncio.sleep(1)

        await self.hass.async_add_job(self._acpartner.learn_stop, slot)
        _LOGGER.error("Timeout. No infrared command captured")
        self.hass.components.persistent_notification.async_create(
            "Timeout. No infrared command captured", title="Xiaomi Miio Remote"
        )

    async def async_send_command(self, command, **kwargs):
        """Send a infrared command."""
        repeat = kwargs[ATTR_NUM_REPEATS]
        delay = kwargs[ATTR_DELAY_SECS]
        first_command = True

        if not command:
            _LOGGER.error("No IR command.")
            return

        for _ in range(repeat):
            if not first_command:
                time.sleep(delay)

            if command.startswith("01"):
                await self._try_command(
                    "Sending new air conditioner configuration failed.",
                    self._acpartner.send_command,
                    command,
                )
            elif command.startswith("FE"):
                if self._air_condition_model is not None:
                    # Learned infrared commands has the prefix 'FE'
                    await self._try_command(
                        "Sending custom infrared command failed.",
                        self._acpartner.send_ir_code,
                        self._air_condition_model,
                        command,
                    )
                else:
                    _LOGGER.error(
                        "Model number of the air condition unknown. "
                        "IR command cannot be sent."
                    )
            else:
                _LOGGER.error("Invalid IR command.")

            first_command = False
