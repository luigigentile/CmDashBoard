from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping, NamedTuple, Sequence, Type

from django.db.models import Q, QuerySet

from cm.data import ranges, units
from cm.db import models
from cm.db.attribute_field.transform import decode_form_value

FLOAT_PRECISION = 0.000000001


@dataclass(frozen=True)
class AttributeQuery:
    class Operator(Enum):
        EXACT = "exact"
        IEXACT = "iexact"
        CONTAINS = "contains"
        ICONTAINS = "icontains"
        STARTSWITH = "startswith"
        ISTARTSWITH = "istartswith"
        ENDSWITH = "endswith"
        IENDSWITH = "iendswith"
        ISNULL = "isnull"
        IN = "in"
        LT = "lt"
        LTE = "lte"
        GT = "gt"
        GTE = "gte"

    class Lookups(NamedTuple):
        """A set of attribute field lookups and the associated attribute names."""

        lookups: Mapping[str, Any]
        attributes: Iterable[str]

    DataTypes = models.AttributeDefinition.DataType

    name: str
    value: Any
    operator: Operator
    attribute_definition: models.AttributeDefinition
    exclude: bool = False

    def __hash__(self) -> int:
        # FIXME: This relies on a stable string representation for the "value" field
        # which won't always be the case although it shouldn't cause any issues for now.
        return hash(
            (self.name, str(self.value), self.operator, self.attribute_definition)
        )

    def __str__(self) -> str:
        return f"{self.name}__{self.operator.value}={str(self.value)}"

    @property
    def field(self) -> str:
        """Get the Django ORM field name for this attribute."""
        if self.attribute_definition.type == models.AttributeDefinition.Type.INTERFACE:
            return "interface_attributes_sets__attributes"
        if self.attribute_definition.type == models.AttributeDefinition.Type.BLOCK:
            return "attributes"
        if self.attribute_definition.type == models.AttributeDefinition.Type.DIRECT:
            return models.DirectAttributeDefinition.BLOCK_LOOKUPS[
                self.attribute_definition.block_attribute
            ]

        raise RuntimeError(f"Unknown attribute type {self.attribute_definition.type}!")

    @property
    def field_filter(self) -> str:
        """Get the Django ORM field name for this attribute."""
        if self.attribute_definition.type == models.AttributeDefinition.Type.DIRECT:
            # Direct attributes filter for their field (as they always target scalar database fields)
            return self.field

        # Everything else queries for field__name, because these queries look inside json containing multiple fields.
        return f"{self.field}__{self.name}" if self.field else self.name

    @property
    def lookup(self) -> Q:
        """Return a Django ORM field lookup mapping for this attribute filter query."""

        if self.attribute_definition.datatype in (
            self.DataTypes.quantity_type,
            self.DataTypes.float_type,
        ):
            attribute_lookups = self._lookup_float()

        elif self.attribute_definition.choices:
            attribute_lookups = self._lookup_choices()

        elif self.attribute_definition.datatype in (
            self.DataTypes.str_type,
            self.DataTypes.str_list_type,
        ):
            attribute_lookups = self._lookup_string()

        elif self.attribute_definition.datatype == self.DataTypes.int_type:
            attribute_lookups = self._lookup_integer()

        elif self.attribute_definition.datatype == self.DataTypes.bool_type:
            attribute_lookups = self._lookup_boolean()

        else:
            raise ValueError(
                f"Unknown filter {self.name} of type {self.attribute_definition.datatype}!"
            )

        if self.attribute_definition.is_direct:
            # Direct attributes are just normal, direct, django field lookups
            lookups = Q(**attribute_lookups.lookups)
        else:
            # For attribute fields, we look for the value and also check that the key exists.
            lookups = (
                # Create a Q object from the given field lookups
                Q(**attribute_lookups.lookups)
                # We also need to ensure that every attribute that we're querying also exists,
                # using the "has_key" lookup. If we don't do this then when using this lookup
                # with exclude() we'll exclude all values _without_ the attributes when
                # we just want to exclude all values that match the lookup.
                & Q(
                    **{
                        f"{self.field}__has_key": name
                        for name in attribute_lookups.attributes
                    }
                )
            )

        # If we're "excluding" based on this filter then negate the lookup
        if self.exclude:
            return ~lookups

        return lookups

    def as_queryset(self) -> QuerySet:
        return models.Block.objects.filter(self.lookup)

    def _lookup_float(self) -> Lookups:
        """Return a Django ORM field lookup mapping for a float attribute (quantities and float).

        For quantities, we want to query for the normalized mangnitude, as that's how values are stored.
        In addition, we need to allow for float imprecision (we can't use decimal because of the
        units library we use.

        If the filter value is a range, we look for values falling within that range.
        If the database value is a range, we check if the filter value falls within that range.
        If both the filter and the database value are ranges, we check if the ranges match.

        For most of these lookups, only the exact lookup is defined, though we might want to define gt/lt later.
        For range lookups on range fields, the default lookup will check that the ranges match exactly.
        The `contains` lookup is also supported here to check if the filter range falls within the db range.
        We might want to add an `intersect` lookup later on.
        """
        field_filters = {}
        field_attributes = [self.name]
        filter_is_range = isinstance(self.value, ranges.Range)

        # Validate operator
        if filter_is_range and self.attribute_definition.is_range:
            supported_operators = [self.Operator.CONTAINS, self.Operator.ISNULL]
        elif not filter_is_range:
            supported_operators = [
                self.Operator.GT,
                self.Operator.LT,
                self.Operator.GTE,
                self.Operator.LTE,
                self.Operator.ISNULL,
            ]
        else:
            supported_operators = []
        self._validate_operator(self.operator, supported_operators=supported_operators)

        if isinstance(
            self.value, (ranges.DiscreteQuantityRange, ranges.ContinuousQuantityRange),
        ):
            float_value_low = float(units.normalize_quantity(self.value.low).magnitude)
            float_value_high = float(
                units.normalize_quantity(self.value.high).magnitude
            )
        elif isinstance(
            self.value, (ranges.DiscreteNumberRange, ranges.ContinuousNumberRange)
        ):
            float_value_low = float(self.value.low)
            float_value_high = float(self.value.high)
        elif isinstance(
            self.value, units.Quantity
        ):  # at this point it's not a range: either Quantity or Float
            float_value_low = float_value_high = float(
                units.normalize_quantity(self.value).magnitude
            )
        else:
            float_value_low = float_value_high = self.value

        if self.attribute_definition.is_range:
            field_attributes = [
                f"{self.name}_min",
                f"{self.name}_max",
            ]
            # For ranges, we want the value to be within the attribute's min and max fields, accounting
            # for float inaccuracy
            if self.operator is not self.Operator.GT:
                field_filters[
                    f"{self.field_filter}_min__lt"
                ] = float_value_low + FLOAT_PRECISION * abs(float_value_low)
            if self.operator is not self.Operator.LT:
                field_filters[
                    f"{self.field_filter}_max__gt"
                ] = float_value_high - FLOAT_PRECISION * abs(float_value_high)

            if (
                isinstance(self.value, ranges.Range)
                and self.operator is self.Operator.EXACT
            ):
                # For an exact match lookup, check the ranges match exactly (except for float inaccuracy)
                field_filters[
                    f"{self.field_filter}_min__gt"
                ] = float_value_low - FLOAT_PRECISION * abs(float_value_low)
                field_filters[
                    f"{self.field_filter}_max__lt"
                ] = float_value_high + FLOAT_PRECISION * abs(float_value_high)
        else:
            # For scalars, we simply lookup the value directly, but still account for float inaccuracy
            if self.operator is self.Operator.EXACT:
                # For exact lookups, allow anything between +/- FLOAT_PRECISION from the target value
                field_filters[
                    f"{self.field_filter}__lt"
                ] = float_value_high + FLOAT_PRECISION * abs(float_value_high)
                field_filters[
                    f"{self.field_filter}__gt"
                ] = float_value_low - FLOAT_PRECISION * abs(float_value_low)
            if self.operator == self.Operator.GT:
                # For greater than, only include values that are definitely larger than the target value
                # (have to be bigger by at least FLOAT_PRECISION
                field_filters[
                    f"{self.field_filter}__{self.operator.value}"
                ] = float_value_low + FLOAT_PRECISION * abs(float_value_low)
            if self.operator == self.Operator.GTE:
                # For greater than or equal, be lenient and also allow values that are slightly smaller than the target
                field_filters[
                    f"{self.field_filter}__{self.operator.value}"
                ] = float_value_low - FLOAT_PRECISION * abs(float_value_low)
            if self.operator == self.Operator.LT:
                # For greater than, only include values that are definitely smaller than the target value
                # (have to be smaller by at least FLOAT_PRECISION
                field_filters[
                    f"{self.field_filter}__{self.operator.value}"
                ] = float_value_high - FLOAT_PRECISION * abs(float_value_low)
            if self.operator == self.Operator.LTE:
                # For less than or equal, be lenient and also allow values that are slightly larger than the target
                field_filters[
                    f"{self.field_filter}__{self.operator.value}"
                ] = float_value_high + FLOAT_PRECISION * abs(float_value_low)
            if self.operator is self.Operator.ISNULL:
                field_filters[f"{self.field_filter}__isnull"] = False

        return self.Lookups(lookups=field_filters, attributes=field_attributes)

    def _lookup_choices(self) -> Lookups:
        """Return a Django ORM field lookup mapping for an attribute with choices."""
        if self.attribute_definition.is_range:
            self._validate_operator(self.operator)
            return self.Lookups(
                lookups={f"{self.field_filter}__icontains": self.value},
                attributes=(self.name,),
            )
        else:
            self._validate_operator(
                self.operator,
                supported_operators=(self.Operator.IN, self.Operator.ISNULL),
            )
            return self.Lookups(
                lookups={f"{self.field_filter}__{self.operator.value}": self.value},
                attributes=(self.name,),
            )

    def _lookup_string(self) -> Lookups:
        """Return a Django ORM field lookup mapping for a string attribute."""
        operator = self.operator
        supported_operators = [
            self.Operator.CONTAINS,
            self.Operator.ICONTAINS,
            self.Operator.ISNULL,
        ]
        if self.attribute_definition.datatype == self.DataTypes.str_type:
            supported_operators += [
                self.Operator.STARTSWITH,
                self.Operator.ISTARTSWITH,
                self.Operator.ENDSWITH,
                self.Operator.IENDSWITH,
            ]
        elif self.attribute_definition.datatype == self.DataTypes.str_list_type:
            # For str lists, we need to change the "exact" lookup to "contains".
            # This is because we want to look for a single value in the list, not for all values.
            if operator is self.Operator.EXACT:
                operator = self.Operator.CONTAINS
        self._validate_operator(operator, supported_operators=supported_operators)
        return self.Lookups(
            lookups={f"{self.field_filter}__{operator.value}": self.value},
            attributes=(self.name,),
        )

    def _lookup_integer(self) -> Lookups:
        """Return a Django ORM field lookup mapping for an integer attribute."""
        self._validate_operator(
            self.operator,
            (
                self.Operator.GT,
                self.Operator.LT,
                self.Operator.GTE,
                self.Operator.LTE,
                self.Operator.ISNULL,
            ),
        )
        if self.attribute_definition.is_range:
            if self.operator in (self.Operator.GT, self.Operator.GTE):
                return self.Lookups(
                    lookups={
                        f"{self.field_filter}_min__{self.operator.value}": self.value
                    },
                    attributes=(f"{self.name}_min",),
                )
            elif self.operator in (self.Operator.LT, self.Operator.LTE):
                return self.Lookups(
                    lookups={
                        f"{self.field_filter}_max__{self.operator.value}": self.value
                    },
                    attributes=(f"{self.name}_max",),
                )
            elif self.operator is self.Operator.ISNULL:
                return self.Lookups(
                    lookups={f"{self.field_filter}__isnull": self.value},
                    attributes=(self.name,),
                )
            else:
                return self.Lookups(
                    lookups={
                        f"{self.field_filter}_min__lte": self.value,
                        f"{self.field_filter}_max__gte": self.value,
                    },
                    attributes=(f"{self.name}_min", f"{self.name}_max"),
                )
        else:
            # For scalars, we support all the usual lookups
            return self.Lookups(
                lookups={f"{self.field_filter}__{self.operator.value}": self.value},
                attributes=(self.name,),
            )

    def _lookup_boolean(self) -> Lookups:
        """Return a Django ORM field lookup mapping for a boolean attribute."""
        self._validate_operator(self.operator)
        if self.attribute_definition.is_range:
            raise RuntimeError(
                f"Ranges not supported for boolean attributes (on {self.name})"
            )
        return self.Lookups(
            lookups={f"{self.field_filter}": self.value}, attributes=(self.name,)
        )

    @classmethod
    def _validate_operator(
        cls, operator: Operator, supported_operators: Sequence[Operator] = ()
    ) -> None:
        """Validate an operator against a sequence of supported operators.
        The exact match operators always needs to be supported."""
        if (
            operator not in (cls.Operator.EXACT, cls.Operator.IEXACT)
            and operator not in supported_operators
        ):
            raise RuntimeError(f"Unsupported attribute lookup operator '{operator}'!")

    @classmethod
    def from_db(
        cls: Type["AttributeQuery"], query: "models.FilterQuery"
    ) -> "AttributeQuery":
        """Build a new attribute query from a filter query model."""
        attribute_name = query.attribute_definition.name
        return cls(
            name=attribute_name,
            value=decode_form_value(
                attribute_name, query.value, query.attribute_definition
            ),
            operator=cls.Operator(query.operator),
            attribute_definition=query.attribute_definition,
        )

    @classmethod
    def from_attribute_encoded(
        cls,
        attribute_definition: models.AttributeDefinition,
        operator: Operator,
        value: str,
        exclude: bool = False,
    ) -> "AttributeQuery":
        """Build a new attribute query from an attribute definition model."""

        # FIXME: Hack alert! We pretend that all attribute definitions are scalar values and not ranges
        # this is purely so that we can use decode_form_value and encode_form_value, but only expect a single value.
        # (for filters, we only allow single values even for attributes with ranges, we don't, for example, allow
        # filtering by checking if one range is contained within another.
        is_range = attribute_definition.is_range
        attribute_definition.is_range = False
        decoded_value = decode_form_value(
            attribute_definition.name, value, attribute_definition
        )
        attribute_definition.is_range = is_range

        return cls(
            name=attribute_definition.name,
            attribute_definition=attribute_definition,
            operator=operator,
            value=decoded_value,
            exclude=exclude,
        )
