"""Constants for the eGauge Pro integration."""

from __future__ import annotations

import logging
from datetime import timedelta

from egauge_async.json.models import RegisterType

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfPressure,
    UnitOfTemperature,
)

DOMAIN = "egauge_pro"
LOGGER = logging.getLogger(__package__)

# Config keys
CONF_HOST = "host"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"  # noqa: S105
CONF_USE_SSL = "use_ssl"
CONF_VERIFY_SSL = "verify_ssl"
CONF_INVERT_SENSORS = "invert_sensors"

# Update cadence
SCAN_INTERVAL = timedelta(seconds=30)  # instantaneous power + cumulative counters

# Watt-seconds -> kWh
WS_TO_KWH = 1.0 / 3_600_000.0

# Instantaneous register type -> HA device class / unit. POWER is by far the
# common case; the rest are supported so the integration is general.
INSTANTANEOUS_DEVICE_CLASS: dict[RegisterType, SensorDeviceClass] = {
    RegisterType.POWER: SensorDeviceClass.POWER,
    RegisterType.VOLTAGE: SensorDeviceClass.VOLTAGE,
    RegisterType.CURRENT: SensorDeviceClass.CURRENT,
    RegisterType.TEMPERATURE: SensorDeviceClass.TEMPERATURE,
    RegisterType.HUMIDITY: SensorDeviceClass.HUMIDITY,
    RegisterType.PRESSURE: SensorDeviceClass.PRESSURE,
}

INSTANTANEOUS_UNIT: dict[RegisterType, str] = {
    RegisterType.POWER: UnitOfPower.WATT,
    RegisterType.VOLTAGE: UnitOfElectricPotential.VOLT,
    RegisterType.CURRENT: UnitOfElectricCurrent.AMPERE,
    RegisterType.TEMPERATURE: UnitOfTemperature.CELSIUS,
    RegisterType.HUMIDITY: PERCENTAGE,
    RegisterType.PRESSURE: UnitOfPressure.PA,
}

# Only POWER registers get the cumulative energy counter.
ENERGY_UNIT = UnitOfEnergy.KILO_WATT_HOUR
