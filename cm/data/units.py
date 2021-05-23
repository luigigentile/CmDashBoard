import re
from numbers import Number
from typing import Callable, Optional, Union

import pint
from pint.errors import DimensionalityError, UndefinedUnitError
from pint.quantity import _Quantity
from pint.unit import _Unit as Unit  # noqa (just here for easier imports)

from .unit_registry import UnitRegistry

NUMBER_REGEX = r"^(?P<number>-?(?:(?:[\d]+(?:\.\d+)?)|inf))"

UNITS = UnitRegistry(autoconvert_offset_to_baseunit=True, on_redefinition="ignore",)

pint.set_application_registry(UNITS)

Quantity = UNITS.Quantity

# Custom units and aliases
UNITS.define("k = kiloohm")
UNITS.define("M = megaohm")
UNITS.define("R = ohm")
UNITS.define("percent = 0.001*count = %")
UNITS.define("ppm = 0.000001*count")
UNITS.define("specctra = 0.1 * um")
UNITS.define("gee = g_0")
# FIXME: We'd like to overwrite celsius to make it prettier in the frontend, but this causes problems in pint.
# Pint will correctly parse these units, but when they get turned into delta units it doesn't know how to parse those.
# UNITS.define('degC = kelvin; offset: 273.15 = celsius = degreeC = °C')

# FIXME: Logarithmic units (e.g. dB) don't currently work so we're storing these in the database as floats instead of
# quantities. Ideally this would be fixed in pint and we could convert dB attributes back into quantities.
UNITS.define("decibel = = db")
UNITS.define("decibel_to_milliwatt = = dBm")
UNITS.define("audio_weighted_decibel = = dBA")

UNITS.define("rtHz = Hz ** 0.5")


# Define unit contexts
"""Contexts define areas in which units are valid. For example, R,k and M are resistance units.
These contexts can be used to restrict the valid units when parsing them, to avoid accepting a
capacitance unit in the context of resistance."""
RESISTANCE = "resistance"
CURRENT = "current"
VOLTAGE = "voltage"
POWER = "power"
CAPACITANCE = "capacitance"
INDUCTANCE = "inductance"
TEMPERATURE = "temperature"
LENGTH = "length"
ANGLE = "angle"
FREQUENCY = "frequency"
TIME = "time"
INFORMATION = "information"
PRESSURE = "pressure"

# Define base units - used for checking if a unit is part of a context. Should always be SI units
BASE_UNITS = {
    RESISTANCE: UNITS.ohm,
    CURRENT: UNITS.A,
    VOLTAGE: UNITS.V,
    POWER: UNITS.W,
    CAPACITANCE: UNITS.F,
    INDUCTANCE: UNITS.H,
    TEMPERATURE: UNITS.degC,
    LENGTH: UNITS.m,
    ANGLE: UNITS.deg,
    FREQUENCY: UNITS.Hz,
    TIME: UNITS.s,
    INFORMATION: UNITS.B,
    PRESSURE: UNITS.Pa,
}

# Default units - used for storing values in the database etc, usually SI units but can be scaled up or down.
DEFAULT_UNITS = dict(
    BASE_UNITS,
    **{
        CAPACITANCE: UNITS.uF,  # using uF because it's a better scale for our data
        LENGTH: UNITS.mm,  # using mm because it's a better scale for our data
    },
)

# Dimensionless units are difficult to normalize, pint will just turn any dimensionless into any other one,
# e.g. reg('1byte').to('deg') -> <Quantity(458.3662361046586, 'degree')>.
# Because of this, we limit normalizing dimensionless quantities to just specific hardcoded units.
DIMENSIONLESS_NORMALIZATIONS = {
    UNITS.Unit("deg"): [
        UNITS.Unit("rad"),
        UNITS.Unit("mrad"),
        UNITS.Unit("deg"),
    ],  # Angles
    UNITS.Unit("bit"): [
        UNITS.Unit("bit"),
        UNITS.Unit("kbit"),
        UNITS.Unit("Mbit"),
        UNITS.Unit("gigabit"),
        UNITS.Unit("byte"),
        UNITS.Unit("kbyte"),
        UNITS.Unit("Mbyte"),
        UNITS.Unit("gigabyte"),
    ],
}


def parse_unit(unit: str) -> Unit:
    return UNITS.Unit(unit)


def parse_quantity(quantity: str, context: str = None) -> _Quantity:
    """Parse a string representing a quantity into a pint quantity.

    Only units that we specifically define because they make sense can be used here.
    See units.UNITS for a full list.

    Args:
        quantity: The raw quantity to be parsed
        context: The context in which to check for a unit. See CONTEXTS for a full list.

    Example::

        >>> parse_quantity('1R')
        array(1.) * ohm

        >>> parse_quantity('100k')
        array(100.) * kiloohm

        parse_quantity('100m', units.RESISTANCE)
        >>>
    """

    # pint will silently convert "ohm" to "1 ohm", but we want to raise an error if no magnitude is supplied.
    # To do that, we simply check that the quantity starts with a number
    if not re.match(NUMBER_REGEX, quantity):
        raise ValueError(
            f"No magnitude supplied in {context or 'quantity'} value '{quantity}'!"
        )

    try:
        # Check for infinity values, needed because pint doesn't successfully parse the "inf" string
        if quantity.startswith("inf"):
            parsed = float("inf") * UNITS(quantity[3:])
        elif quantity.startswith("-inf"):
            parsed = float("-inf") * UNITS(quantity[4:])
        else:
            parsed = UNITS(quantity)
    except UndefinedUnitError as e:
        raise ValueError(f"Unknown unit {e.unit_names}.")

    # Check that the value was parsed to a quantity, and not a float, because we don't want to silently support
    # dimensionless values.
    if isinstance(parsed, Number):
        raise ValueError(f"{quantity} has no unit!")

    # If a context was parsed, make sure the unit matches it. We do this by simply trying to convert to the
    # context's base unit
    if context:
        try:
            parsed.to(BASE_UNITS[context])
        except DimensionalityError:
            raise ValueError(f"Unit {parsed.units} is not a valid {context} unit.")

    return parsed


def parser(context: str) -> Callable[[str], _Quantity]:
    def wrapped(quantity: str) -> _Quantity:
        return parse_quantity(quantity, context=context)

    return wrapped


def normalize_quantity(quantity: _Quantity) -> _Quantity:
    # We need to special-case dimensionless units, because pint will
    # happily translate any dimensionless unit into any other, but we only want to allow specific transformations
    if len(quantity.dimensionality) == 0:
        if quantity.unitless:
            # Plain numbers can never be normalized
            return quantity
        # go through the hardcoded dimensionless normalizations and check if the unit appears in one of them
        unit = quantity.units
        for default_unit, compatible_units in DIMENSIONLESS_NORMALIZATIONS.items():
            if unit in compatible_units:
                return quantity.to(default_unit)
        return quantity

    # Check which context this unit belongs to, if any
    try:
        compatible_units = quantity.compatible_units()
    except KeyError:
        # This unit isn't compatible with anything other than itself
        compatible_units = [quantity.units]

    for context, base_unit in BASE_UNITS.items():
        if base_unit in compatible_units:
            default_unit = DEFAULT_UNITS[context]
            if quantity.units == default_unit:
                return quantity
            return quantity.to(default_unit)
    # The unit isn't part of any context, so we don't need to normalise anything.
    return quantity


def is_number(value: Union[str, _Quantity, Number]) -> bool:
    """Returns True if a value is a (float or int) number, False otherwise."""
    if isinstance(value, Quantity):
        return False
    if isinstance(value, Number):
        return True
    return bool(re.fullmatch(NUMBER_REGEX, value))


def is_unit(value: str) -> bool:
    """Returns True if a value represents a unit, False otherwise."""
    try:
        UNITS.Unit(value)
        return True
    except UndefinedUnitError:
        return False


def get_context(unit_symbol: str) -> Optional[str]:
    """Get the context of a unit, or None if the unit isn't part of a context."""
    unit = UNITS.Unit(unit_symbol)

    # We need to special-case dimensionless units, because pint will
    # happily translate any dimensionless unit into any other, but we only want to allow specific transformations
    if len(unit.dimensionality) == 0:
        # go through the hardcoded dimensionless normalizations and check if the unit appears in one of them
        for (
            _default_unit,
            compatible_dimensionless_units,
        ) in DIMENSIONLESS_NORMALIZATIONS.items():
            if unit in compatible_dimensionless_units:
                compatible_units = compatible_dimensionless_units
        else:
            return None
    else:
        try:
            compatible_units = unit.compatible_units()
        except KeyError:
            # This unit isn't compatible with anything other than itself
            compatible_units = [unit]
    # Now check which context this unit belongs to, if any
    for context, base_unit in BASE_UNITS.items():
        if base_unit in compatible_units:
            return context

    # The unit isn't part of any context.
    return None


def is_comparable(unit: Union[Unit, str], other: Union[Unit, str]) -> bool:
    """Checks if two units are comparable to each other."""
    if isinstance(unit, str):
        unit = UNITS.Unit(unit)
    if isinstance(other, str):
        other = UNITS.Unit(other)

    if unit == other:
        return True

    # We need to special-case dimensionless units, because pint will
    # happily translate any dimensionless unit into any other, but we only want to allow specific transformations
    if len(unit.dimensionality) == 0:
        # go through the hardcoded dimensionless normalizations and check if the unit appears in one of them
        for (
            _default_unit,
            compatible_dimensionless_units,
        ) in DIMENSIONLESS_NORMALIZATIONS.items():
            if (
                unit in compatible_dimensionless_units
                and other in compatible_dimensionless_units
            ):
                return True
        else:
            return False

    # For non-dimensionless units, we simply try to convert from one unit to the other and see if it works.

    try:
        UNITS.Quantity(1, unit).to(other)
        return True
    except DimensionalityError:
        return False
