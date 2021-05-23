from numbers import Number
from typing import Any, Dict

from django.core.exceptions import ValidationError

from cm.data import ranges
from cm.data.units import (
    BASE_UNITS,
    UNITS,
    Quantity,
    get_context,
    is_comparable,
    is_number,
    is_unit,
    normalize_quantity,
    parse_quantity,
)
from cm.db.models.attribute_definition import AttributeDefinition

from .constants import DATATYPE_PREFIX

Q = UNITS.Quantity

SCALAR_DATATYPES = {
    bool: AttributeDefinition.DataType.bool_type,
    int: AttributeDefinition.DataType.int_type,
    float: AttributeDefinition.DataType.float_type,
    str: AttributeDefinition.DataType.str_type,  # also includes enums, which are only treated differently in the UI.
}
REVERSE_SCALAR_DATATYPES = {v: k for k, v in SCALAR_DATATYPES.items()}


def decode_db_value(name, value, datatype):
    """Turn a database value, which is stored with its value and data type separated, into a python value."""
    if value in (None, []):
        return None

    is_range = datatype != "[str]" and (
        datatype.startswith("[") or datatype.startswith("(")
    )
    is_continuous = datatype.startswith("(")
    item_datatype = datatype if not is_range else datatype[1:-1]
    is_quantity = is_unit(item_datatype)
    unit = UNITS(str(item_datatype)) if is_quantity else None

    # Decode list values
    if datatype == "[str]":
        return value

    # Decode ranges
    if is_range and is_continuous and is_quantity:
        assert len(value) == 2, f"Got {len(value)} range values, expected 2!"
        return ranges.ContinuousQuantityRange(
            low=Q(value[0], unit), high=Q(value[1], unit)
        )
    if is_range and not is_continuous and is_quantity:
        assert type(value) in (
            tuple,
            list,
        ), f"Got type {value} for range, expected sequence!"
        return ranges.DiscreteQuantityRange([Q(v, unit) for v in value])
    if is_range and is_continuous and not is_quantity:
        assert len(value) == 2, f"Got {len(value)} range values, expected 2!"
        return ranges.ContinuousNumberRange(low=value[0], high=value[1])
    if is_range and not is_continuous and not is_quantity:
        assert type(value) in (
            tuple,
            list,
        ), f"Got type {value} for range, expected sequence!"
        return ranges.DiscreteNumberRange(values=value)

    # Decode scalar values
    if is_quantity:
        assert isinstance(
            value, Number
        ), f"Got {value} for quantity, expected numeric value!"
        return Q(value, unit)
    if datatype in REVERSE_SCALAR_DATATYPES:
        return value

    raise ValueError(f"{name}: '{value}' is not valid for type {datatype}!")


def db_encoded_to_python(data):
    """Convert a db-encoded attribute field to a python object.

    Attributes are stored in the database with an extra field with information about the attribute datatypes,
    which is necessary to parse the values correctly.
    """
    decoded = {}
    for k, v in data.items():
        # Ignore datatype fields, they'll be accessed separately
        if k.startswith(DATATYPE_PREFIX):
            continue
        # Ignore "_max" fields for ranges, they'll be accessed separately
        if k.endswith("_max"):
            continue

        # Continuous ranges are stored in two separate fields that we need to combine
        if k.endswith("_min"):
            # This is a continuous range field, we need the max as well as the min
            field_name = k.split("_min")[0]
            field_value = v, data[f"{field_name}_max"]
        else:
            field_name = k
            field_value = v

        field_datatype = data[f"{DATATYPE_PREFIX}{field_name}"]
        decoded[field_name] = decode_db_value(field_name, field_value, field_datatype)

    return decoded


def encode_db_value(
    name: str, value: Any, include_type_fields: bool = True
) -> Dict[str, Any]:
    """Validate and convert a value into a dict of its database representation.

    The representation is usually just a dict of {field_name: field_value}, but some fields will
    contain extra fields with datatype information, or a value split into multiple different fields.

    If include_type_fields is False, then information about encoded data types won't be included in the encoded value.
    This is useful for querying, where we just want to look up the plain value.

    The database uses
        [] to encode lists as well as discrete ranges (e.g. [str] for ['banana'], [ohm] for [1R, 1k, 5k])
        () to encode continuous ranges (e.g. (ohm) for 1R..5k)
    """
    # We can't determine the value of empty values, they just get an empty data type.
    if not isinstance(value, Quantity) and value in (None, []):
        return {name: None}

    def _simple_value(
        encoded_value: Any, encoded_datatype: str = None
    ) -> Dict[str, Any]:
        encoded = {
            name: encoded_value,
        }
        if encoded_datatype and include_type_fields:
            encoded[f"{DATATYPE_PREFIX}{name}"] = encoded_datatype
        return encoded

    # Deal with list types first
    if isinstance(value, list):
        # Check that the list only consists of a single type / unit.
        list_types = set([type(v) for v in value])
        if len(list_types) > 1:
            raise ValueError(
                f"Lists of attribute values have to be of a single type, got {list_types}!"
            )
        list_type = list(list_types)[0]

        # We only allow string values in plain lists, everything else should be a Range instance.
        if list_type != str:
            raise ValueError(
                f"Only strings are allowed in plain lists, got {list_type} instead, which should be stored as a Range!"
            )

        return _simple_value(value, "[str]")

    # Deal with ranges
    if isinstance(value, ranges.ContinuousQuantityRange):
        # Continuous ranges get split into two separate fields
        # We normalize the low value and then convert the high value to the same one.
        # if we normalized both of them separately we might end up with different units for units that
        # don't normalize.
        normalized_low = normalize_quantity(value.low)
        encoded: Dict[str, Any] = {
            f"{name}_min": float(normalized_low.magnitude),
            f"{name}_max": float(value._high.to(normalized_low.units).magnitude),
        }
        if include_type_fields:
            # () means continuous range
            encoded[
                f"{DATATYPE_PREFIX}{name}"
            ] = f"({normalize_quantity(value.low).units})"
        return encoded
    if isinstance(value, ranges.DiscreteQuantityRange):
        normalized_unit = normalize_quantity(value._values[0]).units
        normalized = [float(v.to(normalized_unit).magnitude) for v in value._values]
        datatype = f"[{normalize_quantity(value._values[0]).units}]"
        return _simple_value(normalized, datatype)
    if isinstance(value, ranges.ContinuousNumberRange):
        encoded = {
            f"{name}_min": value.low,
            f"{name}_max": value.high,
        }
        if include_type_fields:
            encoded[f"{DATATYPE_PREFIX}{name}"] = "(float)"  # () means continuous range
        return encoded
    if isinstance(value, ranges.DiscreteNumberRange):
        return _simple_value(value._values, "[float]")

    # Deal with scalar values
    if isinstance(value, Quantity):
        normalized = normalize_quantity(value)
        return _simple_value(float(normalized.magnitude), str(normalized.units))  # type: ignore
    if type(value) in SCALAR_DATATYPES:
        return _simple_value(value, SCALAR_DATATYPES[type(value)])

    raise ValueError(f"Cannot db-encode value of unsupported type '{value}'!")


def python_to_db_encoded(data, include_type_fields=True):
    """Convert a python dict of attributes to a db-encoded dict.

    Attributes are stored in the database with an extra field with information about the attribute data types,
    which is necessary to parse the values correctly.

    Example:
        input: {some_attribute: 1k}
        output: {
            some_attribute: 1000
            _datatype_some_attribute: ohm
        }

        input {some_attribute: [1k, 5k]}

        input {
            some_attribute: [Range(1k..5k)],
            other_attribute: [Range(1k,2k,5k)]
        }
        output {
            some_attribute_min: 1000
            some_attribute_max: 5000,
            other_attribute: [1000, 2000, 5000],
            _datatype_some_attribute: ohm,
            _datatype_other_attribute: ohm
        }

    To convert values for querying the database, rather than storing values, pass include_type_fields=False.
    """
    if not isinstance(data, dict):
        if include_type_fields:
            raise RuntimeError(
                "python_to_db_encoded was called with a non-dict object and include_field_types=True. "
                "This should never happen as it suggests we're trying to store something that isn't a dict "
                "in an attribute field!"
            )
        return encode_db_value(
            name="__NONE__", value=data, include_type_fields=include_type_fields
        )

    encoded: Dict[str, Any] = {}
    for k, v in data.items():
        encoded.update(
            encode_db_value(name=k, value=v, include_type_fields=include_type_fields)
        )

    return encoded


def decode_raw_value(name, value, attribute_definition):
    """Decode and validate a JSON value into a python value."""
    datatypes = AttributeDefinition.DataType
    choices = attribute_definition.choices
    datatype = attribute_definition.datatype
    unit_symbol = attribute_definition.unit
    unit = UNITS.Unit(unit_symbol)
    context = get_context(unit_symbol) if unit_symbol else None

    # Decode null values
    if value is None:
        if attribute_definition.is_required:
            raise ValueError(f"{name}: Invalid null value for required field")
        return value

    # Decode lists
    if datatype == datatypes.str_list_type:
        if not isinstance(value, list):
            raise ValueError(f"{name}: Invalid type, must be a list")

        invalid_items = [v for v in value if v not in choices] if choices else []
        if invalid_items:
            invalid_items = [v for v in value if v not in choices]
            raise ValueError(
                f"', '.join({invalid_items}) is invalid! Valid choices are {', '.join(choices)}."
            )
        return value

    # Decode ranges
    if attribute_definition.is_range:
        if not isinstance(value, str):
            raise ValueError(f"{name}: Invalid type, must be a string")

        if datatype in (datatypes.float_type, datatypes.int_type):
            # Continuous and discrete number ranges
            try:
                return ranges.parse_number_range(value)
            except ValueError as e:
                raise ValueError(f"{name}: {e}")

        else:
            # All other ranges must be continuous or discrete quantity ranges
            try:
                return ranges.parse_quantity_range(
                    value, context=context, base_unit=unit
                )
            except ValueError as e:
                raise ValueError(f"{name}: {e}")

    # Decode quantities
    if unit_symbol:
        if not isinstance(value, (str, Number)):
            raise ValueError(f"{name}: Invalid type, must be a string or a number")

        # We want to allow plain numbers as the unit context's base unit, so we fill in that unit if none was provided
        if isinstance(value, Number):
            value = str(value)
        if is_number(value):
            value += str(BASE_UNITS[context]) if context else unit_symbol
        try:
            result = parse_quantity(value, context)
        except ValueError as e:
            raise ValueError(f"{name}: {e}")
        # Check that if the value didn't have a context, input unit and expected unit are comparable
        if not context and result.units != unit:
            if is_comparable(result.units, unit):
                # Translate the value to its standard unit
                result = result.to(unit_symbol)
            else:
                raise ValueError(
                    f"{name}: '{value}' is not a valid {context or unit_symbol or datatype} value!"
                )
        return result

    # Validate strings
    if datatype == datatypes.str_type:
        if not isinstance(value, str):
            raise ValueError(f"{name}: Invalid type, must be a string")

        # We treat strings as a special case to account for enum choices
        if choices and value.strip() not in choices:
            raise ValueError(
                f"{name}: {value} is invalid! Valid choices are {', '.join(choices)}."
            )

    # Validate bools
    if datatype == datatypes.bool_type:
        if not isinstance(value, bool):
            raise ValueError(f"{name}: Invalid type, must be a boolean")

    # Decode scalar types
    if datatype in REVERSE_SCALAR_DATATYPES:
        datatype_class = REVERSE_SCALAR_DATATYPES[datatype]
        try:
            return datatype_class(value)
        except Exception:
            raise ValueError(f"{name}: '{value}' is not a valid {datatype} value!")

    raise ValueError(
        f"{name}: '{value}' is not a valid {context or unit_symbol or datatype} value!"
    )


def decode_form_value(
    name: str, value: Any, attribute_definition: AttributeDefinition
) -> Any:
    """Decode and validate a form value into a python value."""
    datatypes = AttributeDefinition.DataType
    datatype = attribute_definition.datatype

    if datatype == datatypes.str_list_type:
        # Turn the string input into a list
        value = [v.strip() for v in value.split(",") if v.strip()]

    if datatype == datatypes.bool_type:
        # Turn into a boolean by checking for truthy values
        value = value.lower() in ["1", "true", "y"]

    return decode_raw_value(name, value, attribute_definition)


def form_encoded_to_python(data, attribute_definitions, field_name, raise_errors=True):
    decoded: Dict[str, Any] = {}
    errors = []
    for k, v in data.items():
        if k not in attribute_definitions:
            # Extra attributes are stored as is.
            decoded[k] = v
            continue

        attribute_definition = attribute_definitions[k]

        # Check for required fields
        if not v.strip():
            if attribute_definition.is_required:
                errors.append(f'Attribute "{k}" is required!')
            continue

        # Decode the actual value
        try:
            decoded[k] = decode_form_value(k, v, attribute_definition)
        except ValueError as e:
            errors.append(str(e))

    # Explicitly check for boolean values, as bools set to false in a checkbox don't get submitted
    missing_bool_fields = [
        field_name
        for field_name, definition in attribute_definitions.items()
        if definition.datatype == AttributeDefinition.DataType.bool_type
        and field_name not in data
    ]
    for missing_bool in missing_bool_fields:
        decoded[missing_bool] = False

    if errors and raise_errors:
        raise ValidationError({field_name: errors})

    return decoded


def encode_raw_value(value, datatype):
    """Encode a python value into a JSON compatible value."""
    # Encode ranges
    if isinstance(value, ranges.Range):
        return str(value)

    # Encode quantities
    if isinstance(value, Quantity):
        # Denormalize the value into some sensible compact unit
        try:
            value = value.to_compact()
        except IndexError:
            # pint dies when trying to compact units that are too big.
            pass
        # TODO: We should encode this in a custom Quantity class
        return f"{value.magnitude:g}{value.units:~P}"

    return value


def encode_form_value(value, datatype):
    """Encode a python value into a form value."""
    value = encode_raw_value(value, datatype)

    if value is None:
        return ""

    # Encode lists
    if datatype == AttributeDefinition.DataType.str_list_type:
        return ", ".join(value)

    # Encode scalar values
    if isinstance(value, float):
        # Print floats with minimal decimal places
        return f"{value:g}"
    if datatype == AttributeDefinition.DataType.bool_type:
        return value

    return str(value)


def python_to_form_encoded(data, attribute_definitions):
    encoded = {}

    def _field_sorting(item):
        name, definition = item
        return (
            0 if definition.is_required else 1,  # required fields first
            0 if definition.choices else 1,  # then enums
            0
            if definition.datatype == AttributeDefinition.DataType.bool_type
            else 1,  # then checkboxes
            definition.category.level
            if definition.category
            else 0,  # then category tree level
            name,  # then alphabetically
        )

    for attribute_name, definition in sorted(
        attribute_definitions.items(), key=_field_sorting
    ):
        datatype_label = AttributeDefinition.DataType.values[definition.datatype]

        # FIXME: this is an ugly hack to avoid a bug in pint, which doesn't parse its delta units correctly.
        # We should put this and a few similar hacks into a an adapter layer above pint instead.
        if definition.unit:
            unit = UNITS.Unit(definition.unit)
            unit_symbol = (
                f"{unit:~}"  # Format as a unit symbol (Δ°C instead of delta_degC)
            )
            context = get_context(unit)
            if context:
                context = context.capitalize()
        else:
            unit_symbol = ""
            context = None

        encoded[attribute_name] = {
            "value": encode_form_value(
                data.get(attribute_name, ""), datatype=definition.datatype
            ),
            "unit": context or unit_symbol or datatype_label,
            "unit_description": definition.unit_description,
            "is_required": definition.is_required,
            "is_range": definition.is_range,
            "choices": definition.choices,
            "datatype": definition.datatype,
            "category": definition.category,
        }
    return encoded
