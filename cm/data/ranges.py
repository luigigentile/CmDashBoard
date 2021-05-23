"""Helpers for dealing with ranges of quantities, which are formatted as either

**Null range** (a single quantity)::

    <value>
    107.5R (quantity)
    107.5  (number)

**Continuous range** (from..to)::

    <value>..<value>
    1R..15k (quantity)
    1..15   (numbers)

**Discrete range** (comma-separated list of values)::

    <value>,<value>,[...]
    1R, 10k, 15M (quantity)
    -inf, 0, 100 (numbers)

Quantity ranges can be simplified by only specifying a common unit once (on the last item)::

    <number>..<quantity>
    1..10k (equivalent to 1k..10k)

    <number>,<number>,<number>,<quantity>
    1, 5, 10, 100k (equivalent to 1k, 5k, 10k, 100k)
"""
from abc import ABC, abstractclassmethod, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple, Union

from cm.data import units

RangeItem = Union[int, float, units.Quantity]
Q = units.UNITS.Quantity


class Range(ABC):
    """Abstract interface for all ranges.

    All child classes need to implement
        is_continuous
        low
        high
        includes
        from_string
    """

    @property
    @abstractmethod
    def is_continuous(self) -> bool:
        """True if this is a continuous range, False otherwise."""
        raise NotImplementedError()

    @property
    @abstractmethod
    def low(self) -> RangeItem:
        """Low bound (inclusive) of the range."""
        raise NotImplementedError()

    @property
    @abstractmethod
    def high(self) -> RangeItem:
        """High bound (inclusive) of the range."""
        raise NotImplementedError()

    @abstractmethod
    def includes(self, value: RangeItem) -> bool:
        raise NotImplementedError()

    @abstractclassmethod
    def from_string(cls, range_string: str) -> "Range":
        raise NotImplementedError()

    def __str__(self) -> str:
        raise NotImplementedError()


@dataclass(init=False)
class DiscreteRange(Range):
    """Range made up of discrete values.

    range.values contains the list of all values of the range.
    Discrete ranges cannot be empty, and their list of values has to be sorted.
    """

    _values: Tuple[RangeItem, ...]

    def __init__(self, values: Sequence[RangeItem], context: str = None):
        self.values = tuple(values)
        super().__init__()

    def __str__(self) -> str:
        return ", ".join([str(v) for v in self.values])

    @property
    def values(self) -> Tuple[RangeItem, ...]:
        return self._values

    @values.setter
    def values(self, new_values: Sequence[RangeItem]) -> None:
        if not new_values:
            raise ValueError("Empty ranges are not allowed!")
        if list(sorted(new_values)) != list(new_values):
            raise ValueError("Discrete ranges need to be sorted!")
        self._values = tuple(new_values)

    @property
    def is_continuous(self) -> bool:
        return False

    @property
    def low(self) -> RangeItem:
        # Discrete ranges cannot be empty and .values is guaranteeded to be sorted,
        # so we can just return the first element of values
        return self.values[0]

    @property
    def high(self) -> RangeItem:
        # Discrete ranges cannot be empty and .values is guaranteeded to be sorted,
        # so we can just return the last element of values
        return self.values[-1]

    def includes(self, value: RangeItem) -> bool:
        return value in self.values

    @classmethod
    def from_string(
        cls, range_string: str, number_type: type = float
    ) -> "DiscreteRange":
        if "," not in range_string:
            raise ValueError(
                "Invalid discrete range, expected a comma-separated list of values!"
            )

        values = [number_type(v.strip()) for v in range_string.split(",")]
        return cls(values=values)


@dataclass(init=False)
class ContinuousRange(Range):
    """Range made up of continuous values."""

    _low: RangeItem
    _high: RangeItem

    def __init__(self, low: RangeItem, high: RangeItem, context: str = None):
        self._low = low
        self._high = high

        # This check will also make sure that the given units are comparable.
        if low > high:
            raise ValueError(
                f"Got invalid range - low limit {low} is larger than high limit {high}."
            )

        super().__init__()

    def __str__(self) -> str:
        return f"{str(self.low)}..{str(self.high)}"

    @property
    def is_continuous(self) -> bool:
        return True

    @property
    def low(self) -> RangeItem:
        return self._low

    @low.setter
    def low(self, new_low: RangeItem) -> None:
        if new_low > self._high:
            raise ValueError(
                f"Low range limit ({new_low}) cannot be larger than high limit ({self._high})."
            )
        self._low = new_low

    @property
    def high(self) -> RangeItem:
        return self._high

    @high.setter
    def high(self, new_high: RangeItem) -> None:
        if new_high < self._low:
            raise ValueError(
                f"High range limit ({new_high}) cannot be smaller than low limit ({self._low})."
            )
        self._high = new_high

    def includes(self, value: RangeItem) -> bool:
        return self.low <= value <= self.high

    @classmethod
    def from_string(
        cls, range_string: str, number_type: type = float
    ) -> "ContinuousRange":
        if ".." in range_string:  # Lower and upper limit are given
            low_string, high_string = range_string.split("..")

            if not units.is_number(low_string):
                raise ValueError(
                    f"Expected numeric type for low bound of range, got {str(low_string)}!"
                )
            if not units.is_number(high_string):
                raise ValueError(
                    f"Expected numeric type for high bound of range, got {str(high_string)}!"
                )

            low = number_type(low_string)
            high = number_type(high_string)

            return cls(low=low, high=high)

        # Only a single value is given, which we'll interpret as a range from and to the same value.
        if units.is_number(range_string):
            value = number_type(range_string)
        else:
            value = units.parse_quantity(range_string)

        return cls(low=value, high=value)


@dataclass(init=False)
class DiscreteNumberRange(DiscreteRange):
    """Discrete range limited to just numeric values."""

    _values: Tuple[Union[float, int], ...]

    def __init__(self, values: Sequence[Union[float, int]]):
        for value in values:
            if type(value) not in [float, int]:
                raise ValueError(f"Number ranges can only contain numbers, got {value}")
        super().__init__(values)

    @classmethod
    def from_string(
        cls, range_string: str, number_type: type = float
    ) -> "DiscreteNumberRange":
        super_instance = super().from_string(range_string, number_type=number_type)
        return DiscreteNumberRange(super_instance.values)


@dataclass(init=False)
class ContinuousNumberRange(ContinuousRange):
    """Continuous range limited to just numeric values."""

    _low: Union[float, int]
    _high: Union[float, int]

    def __init__(self, low: Union[float, int], high: Union[float, int]):
        if type(low) not in [float, int]:
            raise ValueError(
                f"Expected numeric type for low bound of range, got {str(low)}!"
            )
        if type(high) not in [float, int]:
            raise ValueError(
                f"Expected numeric type for high bound of range, got {str(high)}!"
            )
        super().__init__(low, high)

    @classmethod
    def from_string(
        cls, range_string: str, number_type: type = float
    ) -> "ContinuousNumberRange":
        super_instance = super().from_string(range_string, number_type=number_type)
        return ContinuousNumberRange(super_instance.low, super_instance.high)


@dataclass(init=False)
class DiscreteQuantityRange(DiscreteRange):
    """Discrete range limited to just quantity values."""

    _values: Tuple[units.Quantity, ...]
    context: Optional[str]

    def __init__(
        self,
        values: Sequence[units.Quantity],
        context: str = None,
        base_unit: str = None,
    ):
        self.context = context
        if base_unit:
            base_unit = units.UNITS.Unit(base_unit)
        else:
            base_unit = units.BASE_UNITS[context] if context else None
        processed = []
        for value in values:
            if base_unit and not units.is_comparable(base_unit, value):
                raise ValueError(f"unit {value.units} not valid for context {context}!")
            if not base_unit and units.is_number(value):
                raise ValueError(
                    "Tried to construct a quantity range without any unit or context!"
                )
            processed.append(Q(value, base_unit) if units.is_number(value) else value)
        super().__init__(values)

    @classmethod
    def from_string(
        cls,
        range_string: str,
        number_type: type = float,
        context: str = None,
        base_unit: str = None,
    ) -> "DiscreteQuantityRange":
        if "," not in range_string:
            raise ValueError(
                "Invalid discrete range, expected a comma-separated list of values!"
            )

        # In a discrete range with units, it's allowed to just add the unit on the last item,
        # or sparsly throughout the list. E.g:
        # "1,2R,1,2k,1,2M" resolves to [1R, 2R, 1k, 2k, 1M, 2M].
        # The easiest way of parsing that is by going through the list in reverse, so that we always
        # have the right unit.
        unit = units.BASE_UNITS[context] if context else None
        values: List[RangeItem] = []
        raw_values = [v.strip() for v in range_string.split(",")]
        for value in reversed(raw_values):
            if units.is_number(value):
                if not unit:
                    raise ValueError(
                        "Tried to construct a quantity range with no unit or context!"
                    )
                values.append(Q(number_type(value), unit))
            else:
                quantity = units.parse_quantity(value)
                unit = quantity.units
                values.append(quantity)

        # Remember we reversed the list for ease of processing, so we need to reverse it again.
        values = list(reversed(values))

        return cls(values=values, context=context, base_unit=base_unit)

    def __str__(self) -> str:
        return ", ".join([f"{v.to_compact():~}" for v in self._values])


@dataclass(init=False)
class ContinuousQuantityRange(ContinuousRange):
    """Continuous range limit to just quantity values."""

    _low: units.Quantity
    _high: units.Quantity
    context: Optional[str]

    def __init__(
        self,
        low: units.Quantity,
        high: units.Quantity,
        context: str = None,
        base_unit: str = None,
    ):
        self.context = context
        if base_unit:
            base_unit = units.UNITS.Unit(base_unit)
        else:
            base_unit = units.BASE_UNITS[context] if context else None

        if not base_unit and units.is_number(high):
            raise ValueError(
                "Tried to construct a quantity range without any unit or context!"
            )
        if units.is_number(high):
            if not units.is_number(low):
                raise ValueError(
                    "Got a range with a unit on the lower bound but not the upper. This is invalid!"
                )
            high = Q(high, base_unit)
        if units.is_number(low):
            # Low number takes on the unit of the high number.
            low = Q(low, high.units) if units.is_number(low) else low

        # This check will also make sure that the given units are comparable.
        if low > high:
            raise ValueError(
                f"Got invalid range - low limit {low} is larger than high limit {high}."
            )

        if base_unit and not units.is_comparable(base_unit, low):
            raise ValueError(
                f"low unit {low.units} is not a valid unit for {context or base_unit}!"
            )
        if base_unit and not units.is_comparable(base_unit, high):
            raise ValueError(
                f"high unit {high.units} is not a valid unit for {context or base_unit}!"
            )
        super().__init__(low, high)

    @classmethod
    def from_string(
        cls,
        range_string: str,
        number_type: type = float,
        context: str = None,
        base_unit: str = None,
    ) -> "ContinuousQuantityRange":
        if ".." in range_string:  # Lower and upper limit are given
            low_string, high_string = range_string.split("..")

            if units.is_number(high_string):
                high = number_type(high_string)
            else:
                high = units.parse_quantity(high_string)

            if units.is_number(low_string):
                low = number_type(low_string)
            else:
                low = units.parse_quantity(low_string)

            return cls(low=low, high=high, context=context, base_unit=base_unit)

        # Only a single value is given, which we'll interpret as a range from and to the same value.
        if units.is_number(range_string):
            value = number_type(range_string)
        else:
            value = units.parse_quantity(range_string)

        return cls(low=value, high=value, context=context, base_unit=base_unit)

    def __str__(self) -> str:
        low = self._low.to_compact()
        high = self._high.to_compact()
        return f"{low.magnitude:g}{low.units:~}..{high.magnitude:g}{high.units:~}"


def parse_quantity_range(
    range_string: str, context: str = None, base_unit: str = None
) -> Union[DiscreteQuantityRange, ContinuousQuantityRange]:
    """Parse a quantity range string into a quantity range.

    Args:
        range_string: The raw range to be parsed
        context: The context in which to check for a unit. See CONTEXTS for a full list.

    Example::

        >>> parse_quantity_range('1R..infk')
        ContinuousQuantityRange(low=array(1.) * ohm, high=array(inf) * kiloohm)

        >>> parse_quantity_range('1,2,5R')
        DistinctQuantityRange(array(1.) * ohm, array(2.) * ohm, array(5.) * ohm)
    """

    if ".." in range_string and "," in range_string:
        raise ValueError("Ranges can use .. syntax or commas, not both!")

    if "," in range_string:
        return DiscreteQuantityRange.from_string(
            range_string, context=context, base_unit=base_unit
        )

    return ContinuousQuantityRange.from_string(
        range_string, context=context, base_unit=base_unit
    )


def parse_number_range(
    range_string: str, number_type: type = float
) -> Union[DiscreteNumberRange, ContinuousNumberRange]:
    """Parse a number range string into a number range.

    Example::

        >>> parse_number_range('-inf..inf')
        ContinuousNumberRange(low=-inf, high=inf)

        >>> parse_number_range('1, 3, 5')
        DiscreteNumberRange(1.0, 3.0, 5.0)
    """
    range_string = str(
        range_string
    )  # Just in case simple numbers get passed in without quotes.

    if ".." in range_string and "," in range_string:
        raise ValueError("Ranges can use .. syntax or commas, not both!")

    if "," in range_string:  # Discrete range
        return DiscreteNumberRange.from_string(range_string, number_type)

    # Discrete range (which also includes a range defined through a single value)
    return ContinuousNumberRange.from_string(range_string, number_type)


# NOTE: These aliases need to be defined down here to avoid them being forward references (using strings)
# Usually forward references are fine, but typing.get_type_hints appears to sometimes struggle to resolve these.
NumberRange = Union[DiscreteNumberRange, ContinuousNumberRange]
QuantityRange = Union[DiscreteQuantityRange, ContinuousQuantityRange]
