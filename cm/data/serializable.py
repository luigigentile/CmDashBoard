import dataclasses
import pathlib
from enum import Enum
from typing import Any, Callable, Dict, List, Tuple, Type, TypeVar, Union, cast
from uuid import UUID

from django.db.models import QuerySet

from cm.data import ranges, units, vector
from cm.data.schema import DictField, Field, IgnoreField, ListField, Schema
from cm.db import models
from cm.error_handling import collect_errors
from cm.exceptions import ValidationError

# Type aliases
# A validator is simply a function taking a single value and returning True on success.
Validator = Callable[[Any], bool]

T = TypeVar("T", bound="Serializable")

registry: Dict[str, "Type[Serializable]"] = {}


class SerializableMeta(type):
    @classmethod
    def _class_label(meta, cls: "Type[Serializable]") -> str:
        module_label = cls.__module__.rsplit(".", 1)[1]
        class_name = cls.__name__
        return f"{module_label}.{class_name}"

    def __new__(
        meta, name: str, bases: Tuple[type], class_dict: Dict[str, Any]
    ) -> "SerializableMeta":
        cls = cast("Type[Serializable]", type.__new__(meta, name, bases, class_dict))
        registry[meta._class_label(cls)] = cls
        return cls


class Serializable(metaclass=SerializableMeta):
    """Mixin to make dataclasses serialize and deserialize to/from dict representations.

    All Serializable classes need a SCHEMA attribute which defines how that class is translated to/from raw data.

    Warning:
        When defining the SCHEMA attribute on child classes, you *must not* add type hints.
        On dataclasses, adding type hints will make the constant into a dataclass field, and it will explode.
    """

    SCHEMA: Union[
        Schema, Callable[[], Schema]
    ] = NotImplemented  #: The schema used to generate an instance from data.

    @classmethod
    # @functools.lru_cache()
    def schema(cls) -> Schema:
        if cls.SCHEMA is NotImplemented:
            raise Exception(f"{cls} has no schema defined!")
        if callable(cls.SCHEMA):
            return cls.SCHEMA()
        return cls.SCHEMA

    @classmethod
    def _parse_value(
        cls,
        field: Field,
        value: Any,
        validated_data: Dict[str, Any] = None,
        quote_string: str = "",
    ) -> Any:
        """Parse a single raw value into a validated value that can be used to construct a class instance.

        Args:
            parser: Either a function taking a single value (type constructor), a dictionary or a Serializable.
                If a parser is a dictionary, it needs to have a 'parser' key containing the actual parser.
                If it is a Serializable, this will call `.from_data` on that Serializable type.
            value: The raw value to be parsed
            validator: An optional function taking a single value and returning nothing. This can raise validation
                errors, which can be useful for more complicated tests, for example to enforce data ranges.
            quote_string: A character used for quoted strings - this will be stripped out of string values if they
                start and end with it.
        """
        validated_data = validated_data or {}
        parsed_value: Any
        if isinstance(field.parser, type) and issubclass(field.parser, Serializable):
            # If the field contains a serializable, call from_data on it
            parsed_value = cast(Serializable, field.value_type).from_data(
                value, quote_string=quote_string
            )
        else:
            # This is where we call the actual parser function.
            # If requires_validated_data is specified, the already-parsed data is passed to the parser as well.
            if field.requires_validated_data:
                parsed_value = field.parser(value, validated_data)
            else:
                parsed_value = field.parser(value)

        # Clean up quoted strings. This is a bit of a weird special case, as this method shouldn't really care about
        # the type of the parsed value here. It really should be part of the parser, but because the quote character
        # can be different for different files and some formats (like specctra) define the quote character in a field
        # in the format itself, it would be really difficult to get the appropriate data to the parser.
        if isinstance(parsed_value, str) and len(parsed_value) > 1 and quote_string:
            parsed_value = parsed_value.strip(quote_string)

        # Execute the validator on the parsed value
        field.validator(parsed_value)

        return parsed_value

    @classmethod
    def _get_default_value(cls, field_name: str) -> Any:
        """Get the default value for a parser."""
        field = cls.schema().fields[field_name]
        # If the field defines a default, use that
        if field.default is not None:
            return field.default

        # Otherwise, get the default from the dataclass attribute
        dataclass_field = cls.__dataclass_fields__[field.name]  # type: ignore
        if dataclass_field.default != dataclasses.MISSING:
            default_value = dataclass_field.default
        elif dataclass_field.default_factory != dataclasses.MISSING:
            default_value = dataclass_field.default_factory()
        elif isinstance(field, ListField):
            default_value = []
        elif isinstance(field, DictField):
            default_value = {}
        else:
            default_value = None

        return default_value

    def _get_raw_name(self, attribute_name: str) -> str:
        """Get the name used in raw data for a class attribute."""
        attribute_value = getattr(self, attribute_name)

        if attribute_value in [None, [], {}]:
            raise RuntimeError(
                "_get_field_name used on empty field, this shouldn't happen!"
            )

        for field in self.schema().fields.values():
            if field.name != attribute_name:
                continue

            # Check if the type of the field matches the type of the attribute
            # For lists and dicts we just check a single value to the sake of speed,
            # but this means that heterogenous lists or dicts aren't supported.
            if isinstance(field, ListField):
                test_value = attribute_value[0]
            elif isinstance(field, DictField):
                test_value = attribute_value.values()[0]
            else:
                test_value = attribute_value

            if isinstance(test_value, field.value_type):
                return field.raw_name

        raise ValueError(f"Cannot find schema field for attribute {attribute_name}")

    @classmethod
    def from_data(
        cls: Type[T], data: Union[T, Dict[str, Any]], quote_string: str = ""
    ) -> T:
        """Take a dictionary of raw data and return an instance of the class.

        Returns:
            Serializable: An instance of the Serializable child class.
        """
        # First check if the object is already parsed, and if so just return it.
        if isinstance(data, Serializable):
            return cast(T, data)
        data = cast(Dict[str, Any], data)

        errors: List[str] = []
        validated_data: Dict[
            str, Any
        ] = {}  # the Dict we will use to construct the class instance

        # Process the schema
        for field in cls.schema().fields.values():
            if isinstance(field, IgnoreField):
                continue

            if field.raw_name not in data:
                # Raise an error if the field is required
                if field.name in cls.schema().required_fields:
                    errors.append(f"Required field {field.raw_name} not found in data.")
                    # Note that we still have to assign a value to this field and continue,
                    # to make sure that we capture all errors.

                # Use the parser's default value if given, unless there is already a default value present
                # (This can happen when multiple fields in the schema write to the same attribute)
                if field.name not in validated_data:
                    validated_data[field.name] = cls._get_default_value(field.name)
                continue

            value = data[field.raw_name]

            # Preprocess the data if necessary
            # This can be used for changing the format of raw data to fit a field. An example for this would be a
            # ListField, that represents its value as a comma-separated string
            # In that case, the field might preprocess 'a,b' to ['a', 'b']
            if field.preprocess:
                value = field.preprocess(value)

            if isinstance(field, ListField):
                validated_data.setdefault(field.name, [])
                # Call parse_value for each item in the list
                for v in value:
                    with collect_errors(
                        errors, [ValueError, KeyError, ValidationError]
                    ):
                        validated_data[field.name].append(
                            cls._parse_value(
                                field=field,
                                value=v,
                                validated_data=validated_data,
                                quote_string=quote_string,
                            )
                        )
            elif isinstance(field, DictField):
                # Dict fields are fairly basic - the value of each entry gets deserialized, but we expect the keys
                # to be plain strings.
                validated_data.setdefault(field.name, {})
                for k, v in value.items():
                    with collect_errors(
                        errors, [ValueError, KeyError, ValidationError]
                    ):
                        validated_data[field.name][k] = cls._parse_value(
                            field=field,
                            value=(k, v) if field.requires_dict_key else v,
                            validated_data=validated_data,
                            quote_string=quote_string,
                        )
            else:
                validated_data[field.name] = None  # Only here in case of an exception
                with collect_errors(errors, [ValueError, KeyError, ValidationError]):
                    validated_data[field.name] = cls._parse_value(
                        field=field,
                        value=value,
                        validated_data=validated_data,
                        quote_string=quote_string,
                    )
        # Check if there are extra fields in the data that we didn't use and let the user know those are unsupported.
        raw_schema_fields = [f.raw_name for f in cls.schema().fields.values()]
        extra_fields = set(data.keys()) - set(raw_schema_fields)
        if extra_fields:
            errors.append(
                f"Unknown fields {', '.join(extra_fields)} in {cls.__name__} data. "
                f"Supported fields are {', '.join(raw_schema_fields)}."
            )

        # Construct the instance. At this point, that instance might not be valid, for example some required values
        # might be missing. We construct it anyway, so that we can call _validate on it, to have the chance to collect
        # even more errors at the same time.
        instance = cls(  # type: ignore
            **validated_data
        )

        try:
            # All the class to do additional validation, which can be useful for cross-field validation, for example.
            instance._validate()
        except ValidationError as e:
            # Add the validation errors to the existing list of errors
            errors += e.errors

        if errors:
            # raise all errors as one
            raise ValidationError(errors)

        return instance

    def _serialize_attribute(self, attribute_name: str, attribute_value: Any) -> Any:
        result: Any

        field = self.schema().fields.get(attribute_name)
        assert field, f"Unknown attribute {attribute_name} on {self}!"

        if isinstance(field, ListField):
            # Allow a separate serializer for every item in the list
            result = [self.get_serializer(v)(v) for v in attribute_value]
        elif isinstance(field, DictField):
            # Allow a separate serializer for every item in the dictionary
            result = {k: self.get_serializer(v)(v) for k, v in attribute_value.items()}
        elif isinstance(field, Field):
            result = self.get_serializer(attribute_value)(attribute_value)
        else:
            raise RuntimeError(f"Unknown field type {field.__class__}")

        # Postprocess the data if necessary
        # This can be used for changing the format of raw data to fit a field. An example for this would be a
        # ListField, that represents its value as a comma-separated string
        # In that case, the field might postprocess ['a', 'b'] to 'a,b'
        if field.postprocess:
            result = field.postprocess(result)

        return result

    def is_default(self, value: Any, field: Field) -> bool:
        return bool(value == self._get_default_value(field.name))

    def is_empty(self, value: Any) -> bool:
        """Check whether value is empty. This mostly exist to allow overriding for types with unusual empty values."""
        # This odd check is done instead of `value in [None, [], {}]` because pint breaks when trying to do an in check.
        return (
            value is None
            or isinstance(value, list)
            and value == []
            or isinstance(value, dict)
            and value == {}
        )

    def to_data(self) -> Dict[str, Any]:
        """Convert an instance into a dictionary of raw data."""
        result: Dict[str, Any] = {}

        for field_name, field in self.schema().fields.items():
            # Don't serialize ignored fields
            if isinstance(field, IgnoreField):
                continue

            value = getattr(self, field_name)
            # Don't serialize missing values (not least because we can't tell their type)
            if self.is_empty(value):
                continue

            # Don't serialize default values unless explicitly asked to
            if self.is_default(value, field) and not field.serialize_default:
                continue

            # Get the results for this attribute
            result[field.raw_name] = self._serialize_attribute(field_name, value)

        return result

    def _validate(self) -> None:
        """Subclasses can override this method to check for more complex conditions like mutually exclusive fields."""
        pass

    @classmethod
    def get_serializer(cls, value: Any) -> Callable[[Any], Any]:
        serializers: Dict[type, Callable[[Any], Any]] = {
            bool: lambda v: "on" if v else "off",
            float: lambda v: "{0:g}".format(v),
            str: str,
            int: str,
            list: lambda v: [cls.get_serializer(item)(item) for item in v],
            Serializable: lambda v: v.to_data(),
            units.Unit: lambda v: str(v),
            units.Quantity: lambda v: [str(v.units), "{0:g}".format(v.magnitude)],
            Enum: lambda v: v.value,
            vector.Vector: lambda v: {
                "x": cls.get_serializer(v.x)(v.x),
                "y": cls.get_serializer(v.y)(v.y),
                "z": cls.get_serializer(v.z)(v.z),
            },
            pathlib.Path: str,
            ranges.Range: str,
            models.Block: lambda v: v.id,
            UUID: lambda v: str(v),
            # FIXME: Currently we're just ignoring querysets on components and serializing them as null
            QuerySet: lambda v: None,
        }

        for field_type, serializer in serializers.items():
            if isinstance(value, field_type):
                return serializer

        raise RuntimeError(f"No serializer for value {value} of type {type(value)}")
