"""The Xiaomi Air Conditioning Companion component."""
# pylint: disable=import-error
import logging

import homeassistant.helpers.config_validation as cv
from homeassistant.const import (
    CONF_HOST,
    CONF_TOKEN
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import PlatformNotReady
from miio import (  # pylint: disable=import-error
    AirConditioningCompanion,
    AirConditioningCompanionV3,
    DeviceException
)

from .const import (
    CONF_MODEL,
    DATA_KEY,
    DOMAIN,
    DOMAINS,
    MODELS_MIIO,
    MODEL_LUMI_ACPARTNER_V3
)

_LOGGER = logging.getLogger(__name__)

async def async_setup(hass: HomeAssistant, hass_config: dict):
    """Set up the Xiaomi Air Conditioning Companion Component."""

    return True


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry):
    """ Update Optioins if available """
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """ check unload integration """
    return all([
        await hass.config_entries.async_forward_entry_unload(entry, domain)
        for domain in DOMAINS
    ])


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Support Xiaomi Air Conditioning Companion Component."""
    # pylint: disable=too-many-statements, too-many-locals
    # migrate data (also after first setup) to options
    if entry.data:
        hass.config_entries.async_update_entry(entry, data={},
                                               options=entry.data)

    # add update handler
    if not entry.update_listeners:
        entry.add_update_listener(async_update_options)

    if entry.data.get(CONF_HOST, None):
        host = entry.data[CONF_HOST]
        token = entry.data[CONF_TOKEN]
        model = entry.data.get(CONF_MODEL)
    else:
        host = entry.options[CONF_HOST]
        token = entry.options[CONF_TOKEN]
        model = entry.options.get(CONF_MODEL)

    if DATA_KEY not in hass.data:
        hass.data.setdefault(DATA_KEY, {})
        hass.data[DATA_KEY][host] = {}

    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}

    if model is None:
        try:
            miio_device = AirConditioningCompanion(host, token)
            device_info = await hass.async_add_executor_job(miio_device.info)
            model = device_info.model
            _LOGGER.info(
                "%s %s %s detected",
                model,
                device_info.firmware_version,
                device_info.hardware_version,
            )
        except DeviceException as ex:
            raise PlatformNotReady from ex

    if model in MODELS_MIIO:
        if model == MODEL_LUMI_ACPARTNER_V3:
            acpartner = AirConditioningCompanionV3(host, token)
        else:
            acpartner = AirConditioningCompanion(host, token)
    else:
        _LOGGER.error(
            "Unsupported device found! Please create an issue at "
            "https://github.com/rytilahti/python-miio/issues "
            "and provide the following data: %s",
            model,
        )
        return False

    hass.data[DOMAIN][host] = acpartner

    # init setup for each supported domains
    await hass.config_entries.async_forward_entry_setups(entry, DOMAINS)

    return True
