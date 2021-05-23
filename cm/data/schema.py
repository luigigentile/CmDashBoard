from collections import defaultdict
from typing import (
    Any,
    Callable,
    DefaultDict,
    Dict,
    List,
    Optional,
    Type,
    TypeVar,
    Union,
    get_type_hints,
)

from cm.exceptions import SchemaError
from cm.typing_utils import resolve_type
from cm.unbound_function import F

ParserType = Callable[..., Any]
AttributeType = Union[List[type], Dict[Type[str], type], type]
T = TypeVar("T")
FieldPreprocessor = Callable[[Any], Any]
FieldPostprocessor = Callable[[Any], Any]
DictPreprocessor = Callable[[object], Dict[str, Any]]
DictPostprocessor = Callable[[Dict[str, Any]], object]
ListPreprocessor = Callable[[object], List[Any]]
ListPostprocessor = Callable[[List[Any]], object]


def _field_ordering(processing_order: List[str]) -> Callable[["Field"], int]:
    """Helper function to sort the fields on a schema according to a processing order list.

    Returns a function that can be used as the `key` on a sorting operation when sorting schema fields.

    The resulting function will return the index of a field in processing_order, making sure that those fields
    are processed in the correct order. For fields without an explicit ordering, this simply returns an arbitray number.
    """
    lookup: DefaultDict[str, int] = defaultdict(lambda: 1000000)
    for field_name in processing_order:
        lookup[field_name] = processing_order.index(field_name)

    return lambda field: lookup[field.name]


class Field:
    name: str  #: The name of this field in the serializable class
    parser: F[ParserType]  #: Factory taking a single argument (the raw field value)
    validator: F[Callable[[Any], bool]]  #: Optional validator for parsed values
    raw_name: str  #: The name for this field in the raw data, usually the same as `name`.
    value_type: type  #: The type of a single value in the field.
    default: Optional[Any]
    serialize_default: bool  #: Set to true to serialize optional values even if they match the default.
    requires_validated_data: bool  #: Set to true to pass along already validated data when parsing data for a field.

    preprocess: F[Optional[FieldPreprocessor]]
    postprocess: F[Optional[FieldPostprocessor]]

    @staticmethod
    def _null_validator(v: Any) -> bool:
        return True

    def __init__(
        self,
        name: str,
        parser: ParserType,
        *,
        raw_name: str = None,
        default: Any = None,
        validator: Callable[[Any], bool] = None,
        serialize_default: bool = False,
        value_type: type = None,
        requires_validated_data: bool = False,
        preprocess: FieldPreprocessor = None,
        postprocess: FieldPostprocessor = None,
    ):
        self.name = name
        self.parser = parser
        self.validator = validator if validator else self._null_validator
        self.raw_name = raw_name or name
        self.default = default
        self.serialize_default = serialize_default
        self.requires_validated_data = requires_validated_data
        self.value_type = self._get_value_type(name, parser, value_type)

        # Pre/post-processing on plain fields doesn't do anything, child classes overwrite these
        self.preprocess = preprocess
        self.postprocess = postprocess

        self.validate()

    def validate(self) -> None:
        """Validate that this schema field is configured correctly."""

        # Serializing default values only makes sense if there is a default value
        if self.default is None and self.serialize_default:
            raise SchemaError(
                f"Schema field {self} has no default but specifies serialize_default=True, which is invalid."
            )

        # If a field preprocesses its data when deserializing it, it also has to postprocess the data when serializing.
        if self.preprocess and not self.postprocess:
            raise SchemaError(
                f"Schema field {self} has a pre- but no postprocessor, please add a postprocessor!"
            )
        if self.postprocess and not self.preprocess:
            raise SchemaError(
                f"Schema field {self} has a post- but no preprocessor, please add a preprocessor!"
            )

    def __repr__(self) -> str:
        return f"{self.name}"

    @classmethod
    def _get_value_type(
        cls, name: str, parser: ParserType, value_type: Optional[type]
    ) -> type:
        if isinstance(parser, type):
            if value_type:
                raise SchemaError(
                    f"Schema field {cls} {parser} uses a type constructor for its parser, but also specifies a type. "
                    "This is unsupported, as the parser already defines the field's type."
                )
            return parser
        elif not value_type:
            # The parser isn't a type constructor and no explicit type is given, but we can get the type from
            # the parser's type hints if any are given.
            type_hints = get_type_hints(parser)
            if "return" in type_hints:
                resolved_type = resolve_type(type_hints["return"])
                if not isinstance(resolved_type, type):
                    raise SchemaError(
                        f"Schema field {name} parser unsupported return type {resolved_type}. "
                        "Parsers should return a single, non-sequence type."
                    )
                return resolved_type
            raise SchemaError(
                f"Schema field {cls} {parser} doesn't use a type constructor nor specifies an explicit type. "
                "Please use a type constructor, add a value_type to the field, or add type hints to the parser"
            )
        else:
            return value_type


class ListField(Field):
    """ListFields contain many values of field.value_type.

    The type of the class attribute using this field should be List[field.value_type]."""

    preprocess: F[Optional[ListPreprocessor]]
    postprocess: F[Optional[ListPostprocessor]]

    def __init__(
        self,
        name: str,
        parser: ParserType,
        *,
        raw_name: str = None,
        default: Any = None,
        validator: Callable[[Any], bool] = None,
        serialize_default: bool = False,
        value_type: type = None,
        requires_validated_data: bool = False,
        preprocess: ListPreprocessor = None,
        postprocess: ListPostprocessor = None,
    ):
        super().__init__(
            name,
            parser,
            raw_name=raw_name,
            default=default,
            validator=validator,
            serialize_default=serialize_default,
            value_type=value_type,
            requires_validated_data=requires_validated_data,
            preprocess=preprocess,
            postprocess=postprocess,
        )


class DictField(Field):
    """DictFields contain many values of field.value_type, in a mapping of str -> field.value_type.

    The type of the class attribute using this field should be Dict[str, field.value_type]."""

    requires_dict_key: bool = False

    preprocess: F[Optional[DictPreprocessor]]
    postprocess: F[Optional[DictPostprocessor]]

    def __init__(
        self,
        name: str,
        parser: ParserType,
        *,
        raw_name: str = None,
        default: Any = None,
        validator: Callable[[Any], bool] = None,
        serialize_default: bool = False,
        value_type: type = None,
        requires_validated_data: bool = False,
        requires_dict_key: bool = False,
        preprocess: DictPreprocessor = None,
        postprocess: DictPostprocessor = None,
    ):
        """DictField takes an extra argument called `requires_dict_key`.

        This controls whether the parser requires they key of the passed-in value, in which case the parser will be
        called with an argument in the shape of `(dict_key, dict_value)` instead of just `dict_value`.
        """
        self.requires_dict_key = requires_dict_key
        super().__init__(
            name,
            parser,
            raw_name=raw_name,
            default=default,
            validator=validator,
            serialize_default=serialize_default,
            value_type=value_type,
            requires_validated_data=requires_validated_data,
            preprocess=preprocess,
            postprocess=postprocess,
        )


class IgnoreValue:
    """Sentinel type for values of IgnoreField, which should be ignored when processing."""


class IgnoreField(Field):
    """Special field type for values that shouldn't be parsed, but simply ignored."""

    def __init__(
        self,
        name: str,
        parser: ParserType = None,
        *,
        raw_name: str = None,
        default: Any = None,
        validator: Callable[[Any], bool] = None,
        serialize_default: bool = False,
        value_type: type = None,
        requires_validated_data: bool = False,
    ):
        self.raw_name = raw_name or name
        self.name = name
        self.value_type = IgnoreValue


class Schema:
    """The Schema of a serializable class describes how raw data is mapped to and from class data.

    The schema consists of fields, which each field describing how to create instance data from raw data,
    and how to serialize instance data back into serialized data.

    Note that the `fields` dictionary, used for accessing the fields of the schema, is always sorted according to
    the processing_order argument.

    Args:
        processing_order: A list of field names that need to be processed first, and in a particular order.
            Other fields are processed in an arbitrary order.
        required_fields: A list of field names that specify which fields are required for deserialization.
            Note that these do not have to match the required/optional fields on the class itself,
            though fields that are required on the class and don't have a default value set in the schema field
            must be required.

    """

    fields: Dict[str, Field]
    processing_order: List[str]
    required_fields: List[str]

    def __init__(
        self,
        fields: List[Field],
        *,
        processing_order: List[str] = None,
        required_fields: List[str] = None,
    ) -> None:
        self.processing_order = processing_order or []
        self.required_fields = required_fields or []
        self.fields = {
            field.name: field
            for field in sorted(fields, key=_field_ordering(self.processing_order))
        }

        # Schema-level validation

        # All fields using the same attribute name must have the same field type (e.g. ListField),
        # and each field must have a _different_ value type.
        # If this isn't the case, it's not possible to map attribute values back to fields.
        value_types: Dict[str, type] = {}
        field_types: Dict[str, type] = {}
        for field in fields:
            if isinstance(field, IgnoreField):
                continue

            if field.name in value_types:
                if value_types[field.name] == field.value_type:
                    raise SchemaError(
                        f"Invalid schema in {self}, attribute name {field.name} is used multiple times "
                        f"with the same type ({field.value_type}). This is unsupported, as it would not be "
                        f"possible to serialize this field."
                    )
                if field_types[field.name] != type(field):
                    raise SchemaError(
                        f"Invalid schema in {self}, attribute name {field.name} is used multiple times "
                        f"with different field types ({field_types[field.name]} and {type(field)}. "
                        f"This is unsupported as it would require the model field to be of two different types."
                    )
            else:
                value_types[field.name] = field.value_type
                field_types[field.name] = type(field)

    def serialize_default(self, field_name: str) -> bool:
        """Helper to make it easier to access serialize_default on a field."""
        return self.fields[field_name].serialize_default

    def get_name_from_raw_name(self, raw_name: str) -> str:
        for field in self.fields.values():
            if field.raw_name == raw_name:
                return field.name
        raise RuntimeError(f"Unknown raw field name {raw_name}!")
