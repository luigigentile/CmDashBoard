import functools
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, cast

from cm.data.schema import IgnoreValue, ListField
from cm.data.serializable import Serializable


class LispSerializable(Serializable):
    LISP_SCHEMA: List[str] = NotImplemented

    @classmethod
    @functools.lru_cache()
    def lisp_schema(cls) -> "LispSchema":
        """Get the lisp schema for this class

        Returns:
            The schema for this class, without meta fields.
        """
        return LispSchema.parse(cls.LISP_SCHEMA)

    @classmethod
    def _field_ordering(cls, item: Tuple[str, Any]) -> float:
        """Return an ordering index for a field.

        For fields that don't have an order specified, this is simply a very large number.
        Otherwise, is the field's index in _field_processing_order
        """
        # Lisp serializables have an index for every field, unlike serializables in general.
        raw_field_name, value = item

        schema_item_names = [item.raw_field_names for item in cls.lisp_schema().items]

        for index, schema_item in enumerate(schema_item_names):
            if raw_field_name in schema_item:
                # This is quite a hack - but we need to make sure that fields with multiple field names
                # are ordered stably. For example {rect|path} has the same index here, as both rect and path
                # are part of the same item. But we want rect to always come before path, so we add a slight additional
                # sorting weight to the position of the item itself.
                # Path in this case would come back as 1.01 and rect as 1.00 (if index is 1)
                return index + schema_item.index(raw_field_name) / 100

        raise ValueError(f"Unknown lisp schema item {raw_field_name}")

    @classmethod
    def get_tokens(
        cls, items: List["LispItem"], data: List[Any], num_item_matches: int
    ) -> Optional[List[Any]]:
        current_item = items[0]
        next_items = items[1:]
        candidate_tokens = data[: current_item.length]

        if not data:
            return None
        if num_item_matches > 0 and not current_item.is_list:
            return None
        if cls.lisp_schema().item_matches(current_item, next_items, candidate_tokens):
            return candidate_tokens
        return None

    @staticmethod
    def _quote_string(s: str, quote_string: str) -> str:
        if s == "" or any([char in s for char in ["(", ")", " "]]):
            return f"{quote_string}{s}{quote_string}"
        return s

    @classmethod
    def dict_to_lisp(cls, data: Dict[str, Any], quote_string: str = "") -> List[Any]:
        result: List[Any] = []

        sorted_data = sorted(data.items(), key=cls._field_ordering)
        lisp_schema = cls.lisp_schema()
        serializable_schema = cls.schema()

        for raw_field_name, value in sorted_data:
            field_name = serializable_schema.get_name_from_raw_name(raw_field_name)
            field_value_type = serializable_schema.fields[field_name].value_type
            schema_item = lisp_schema.get_item(raw_field_name)

            if not isinstance(value, list):
                # Coerce single-item values into a list, which simplifies handling
                value = [value]

            if issubclass(field_value_type, LispSerializable):
                # Recurse down into the next Serializable
                for v in value:
                    if schema_item.is_atom:
                        result += field_value_type.dict_to_lisp(v, quote_string)
                    else:
                        result.append(
                            [
                                raw_field_name,
                                *field_value_type.dict_to_lisp(v, quote_string),
                            ]
                        )
            else:
                # Quote any strings that need quoting
                value = [
                    cls._quote_string(v, quote_string) if field_value_type == str else v
                    for v in value
                ]
                if schema_item.is_atom:
                    result += value
                else:
                    result.append([raw_field_name, *value])

        return result

    @classmethod
    def lisp_to_dict(cls, data: List[Any]) -> Dict[str, Any]:
        lisp_schema = cls.lisp_schema()
        serializable_schema = cls.schema()
        result: Dict[str, Any] = {}

        remaining_data = data[:]
        for item_index, current_item in enumerate(lisp_schema.items):
            num_item_matches = 0
            while True:
                tokens = cls.get_tokens(
                    lisp_schema.items[item_index:], remaining_data, num_item_matches
                )
                if not tokens:
                    break
                # Using up these tokens, remove them from the data
                remaining_data = remaining_data[current_item.length :]
                num_item_matches += (
                    1  # The item has been used (at least once in the case of a list)
                )

                raw_field_name = current_item.get_raw_name(tokens)
                field_name = serializable_schema.get_name_from_raw_name(raw_field_name)
                field_value_type = serializable_schema.fields[field_name].value_type

                # The value of the field is either
                # - the first token for a normal atom
                # - all tokens for an atom with a length > 1
                # - all tokens except the first for a non-atom (removing the sub-expression)
                # - in special circumstances, all tokens except the first n
                #       This happens in some formats with weird lisp, where expressions are made up of
                #       multiple tokens.
                if current_item.is_atom:
                    field_value = tokens[0] if current_item.length == 1 else tokens
                else:
                    # An expression should only ever be a single token long, but some formats (looking at you, kicad),
                    # have expressions that contain spaces and so fill up multiple tokens.
                    # In these cases, we just chop off as many tokens as there are words in the field name.
                    expression_length = raw_field_name.count(" ") + 1
                    field_value = tokens[0][expression_length:]

                # Recurse down if this is a LispSerializable
                if issubclass(field_value_type, LispSerializable):
                    field_value = field_value_type.lisp_to_dict(field_value)
                elif issubclass(field_value_type, IgnoreValue):
                    field_value = None
                elif (
                    isinstance(field_value, list)
                    and current_item.length == 1
                    and not isinstance(
                        serializable_schema.fields[field_name], ListField
                    )
                ):
                    field_value = field_value[0]

                if current_item.is_list:
                    result.setdefault(raw_field_name, []).append(field_value)
                else:
                    result[raw_field_name] = field_value
            if not num_item_matches and not current_item.is_optional:
                raise ValueError(
                    f"Invalid lisp schema in {cls}. Expected non-optional item {current_item.raw_field_names}, "
                    f"but received non-matching data {remaining_data}."
                )
        if remaining_data:
            # Check if we used up all data
            raise ValueError(
                f"Invalid lisp schema in {cls}. Found extra unexpected data {remaining_data} "
                f"in lisp schema {lisp_schema}"
            )
        return result


@dataclass
class LispItem:
    _lisp_schema: str
    raw_field_names: List[str]
    is_optional: bool
    is_list: bool
    is_atom: bool
    length: int

    def get_raw_name(self, tokens: List[Any]) -> str:
        if self.is_atom:
            return self.raw_field_names[0]
        return cast(str, tokens[0][0])

    def name_matches(self, tokens: List[Any]) -> bool:
        """Check if a field name matches the list of tokens.

        Usually this is just `tokens[0][0] in self.raw_field_names`.
        However, field names can in certain formats with wonky lisp be made up of multiple tokens.
        In those cases, we have to check multiple tokens.
        """
        for name in self.raw_field_names:
            name_length = name.count(" ") + 1
            if " ".join(tokens[0][:name_length]) == name:
                return True
        return False

    def __post_init__(self) -> None:
        if not self.is_atom:
            assert self.length == 1, "Non-atomic lisp items must have length 1"
        if self.is_atom:
            assert (
                len(self.raw_field_names) == 1
            ), "Atomic lisp items must have a single unambiguous field name!"


@dataclass
class LispSchema:
    _lisp_schema: List[str]
    items: List[LispItem]

    def get_item(self, field_name: str) -> LispItem:
        for item in self.items:
            if field_name in item.raw_field_names:
                return item
        raise ValueError(f"Unknown lisp item {field_name}")

    @classmethod
    def parse(cls, lisp_schema: List[str]) -> "LispSchema":
        items: List[LispItem] = []
        for item_data in lisp_schema:
            processed_data = item_data

            # Set up defaults for item
            is_optional = False
            is_list = False
            is_atom = True
            length = 1

            # Optional - '?<token>'
            if processed_data.startswith("?"):
                is_optional = True
                processed_data = processed_data[1:]

            # List - '[<token>]'
            if processed_data.startswith("[") and processed_data.endswith("]"):
                is_list = True
                processed_data = processed_data[1:-1]

            # dict - '{<token>}'
            if processed_data.startswith("{") and processed_data.endswith("}"):
                is_atom = False
                processed_data = processed_data[1:-1]

            # Length indicator - [n]<token>
            if processed_data.startswith("["):
                m = re.match(r"\[(?P<length>\d+)\]", processed_data)
                if not m:
                    raise Exception("Invalid length indicator in lisp schema")
                length = int(m.groupdict()["length"])
                processed_data = processed_data.split("]", 1)[1]

            # we should now have just a names left, separated with |
            raw_field_names = processed_data.split("|")

            items.append(
                LispItem(
                    _lisp_schema=item_data,
                    raw_field_names=raw_field_names,
                    is_optional=is_optional,
                    is_list=is_list,
                    is_atom=is_atom,
                    length=length,
                )
            )

        return cls(_lisp_schema=lisp_schema, items=items,)

    def item_matches(
        self, current_item: LispItem, remaining_items: List[LispItem], tokens: List[Any]
    ) -> bool:
        # If the item isn't an atom, we can know with confidence whether it matches, by just checking the expression
        # of the first token, which should match the field name
        if not current_item.is_atom:
            return current_item.name_matches(tokens)

        # If it is an atom, if it's required (and not a list) we just have to assume that it matches
        if not current_item.is_optional and not current_item.is_list:
            return True

        # If the current item is both an atom and optional, we should check if any next item might match,
        # as long as they are optional
        for item in remaining_items:
            if item.is_atom:
                # If multiple optional atoms follow each other, we have to assume the current one matches.
                # Theres no way to distinguish which of multiple optional atoms is present.
                return True
            if item.name_matches(tokens):
                # The token matches another item further down the line, so it doesn't match this one.
                return False
            elif not item.is_optional:
                # The next token isn't an atom, doesn't match the current token and it's required,
                # so it has to be part of the current item.
                return True
        # Nothing else seems to fit this token, so it has to be ours
        return True
