"""Constants of the Xiaomi Air Conditioning Companion component."""
from datetime import timedelta
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass
)

from homeassistant.const import (
    POWER_WATT
)

DEFAULT_NAME = "Xiaomi Air Conditioning Companion"
DOMAIN = "xiaomi_miio_airconditioningcompanion"
DOMAINS = ["climate", "sensor"]
DATA_KEY = "xiaomi_miio_airconditioningcompanion_data"
DATA_STATE = "state"
DATA_DEVICE = "device"

CONF_COMMAND = "command"
CONF_HUMIDITY_SENSOR = 'humidity_sensor'
CONF_POWER_SENSOR = 'power_sensor'
CONF_TEMPERATURE_SENSOR = 'temperature_sensor'
CONF_MIN_TEMP = "min_temp"
CONF_MAX_TEMP = "max_temp"
CONF_MODEL = "model"
CONF_MAC = "mac"
CONF_SLOT = "slot"

DEFAULT_TIMEOUT = 10
DEFAULT_SLOT = 30
DEFAULT_DELAY = 1
TARGET_TEMPERATURE_STEP = 1
DEFAULT_TARGET_TEMPERATURE = 26

ATTR_AIR_CONDITION_MODEL = "ac_model"
ATTR_SWING_MODE = "swing_mode"
ATTR_FAN_MODE = "fan_mode"
ATTR_LOAD_POWER = "load_power"
ATTR_LED = "led"
ATTR_POWER = "power"
ATTR_IS_ON = "is_on"
ATTR_BRAND = "air_condition_brand"
ATTR_CONFIGURATION = "air_condition_configuration"
ATTR_REMOTE_NUMBER = "air_condition_remote"
ATTR_DEVICE_TYPE = "device_type"

MODEL_LUMI_ACPARTNER_V1 = "lumi.acpartner.v1"
MODEL_LUMI_ACPARTNER_V2 = "lumi.acpartner.v2"
MODEL_LUMI_ACPARTNER_V3 = "lumi.acpartner.v3"

OPT_MODEL = {
    MODEL_LUMI_ACPARTNER_V1: "Aqara Air Conditioning Companion",
    MODEL_LUMI_ACPARTNER_V2: "Xiaomi Mi Air Conditioner Companion",
    MODEL_LUMI_ACPARTNER_V3: "Xiaomi/Aqara Air Conditioning Companion"
}

MODELS_MIIO = [
    MODEL_LUMI_ACPARTNER_V1,
    MODEL_LUMI_ACPARTNER_V2,
    MODEL_LUMI_ACPARTNER_V3
]

MODELS_ALL_DEVICES = MODELS_MIIO

DEFAULT_SCAN_INTERVAL = 60
SCAN_INTERVAL = timedelta(seconds=DEFAULT_SCAN_INTERVAL)

ACPARTNER_PROPS = [
    ATTR_AIR_CONDITION_MODEL,
    ATTR_FAN_MODE,
    ATTR_LED,
    ATTR_POWER,
    ATTR_SWING_MODE,
    ATTR_LOAD_POWER,
]

@dataclass
class XiaomiACPartnerSensorDescription(
    SensorEntityDescription
):
    """Class to describe an Xiaomi Air Conditioning Companion sensor."""


ACPARTNER_SENSORS: tuple[XiaomiACPartnerSensorDescription, ...] = (
    XiaomiACPartnerSensorDescription(
        key=ATTR_IS_ON,
        name="Status",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:chip"
    ),
    XiaomiACPartnerSensorDescription(
        key=ATTR_LOAD_POWER,
        name="Load Power",
        native_unit_of_measurement=POWER_WATT,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:flash"
    ),
    XiaomiACPartnerSensorDescription(
        key=ATTR_BRAND,
        name="Climate Brand",
        icon="mdi:watermark"
    ),
    XiaomiACPartnerSensorDescription(
        key=ATTR_CONFIGURATION,
        name="Climate Configuration",
        icon="mdi:air-conditioner"
    ),
    XiaomiACPartnerSensorDescription(
        key=ATTR_REMOTE_NUMBER,
        name="Climate Remote Number",
        icon="mdi:remote"
    ),
    XiaomiACPartnerSensorDescription(
        key=ATTR_DEVICE_TYPE,
        name="Device Type",
        icon="mdi:devices"
    )
)
