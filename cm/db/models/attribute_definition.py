from enum import Enum

from django.contrib.postgres import fields as postgres_fields
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Manager
from django.db.models.expressions import Func
from djchoices import ChoiceItem, DjangoChoices

from cm.data.units import UndefinedUnitError, parse_unit
from cm.db.constants import BlockAttribute
from cm.db.fields import SmallTextField

from .base_model import BaseModel


class JsonKeys(Func):
    function = "jsonb_object_keys"


def part_number_values(block):
    from cm.db import models

    return models.ManufacturerPart.objects.filter(part=block).values_list(
        "part_number", flat=True
    )


def manufacturer_values(block):
    from cm.db import models

    return models.Manufacturer.objects.filter(manufacturerpart__part=block).values_list(
        "name", flat=True
    )


class AttributeDefinition(BaseModel):
    """Describes an attribute required by / supported for an interface or part category."""

    class Meta:
        ordering = ("name", "id")

    class Type(Enum):
        DIRECT = "direct"  # Direct block attributes
        BLOCK = "block"  # Attribute field on block
        INTERFACE = "interface"  # Attribute field on interface

    class DataType(DjangoChoices):
        str_type = ChoiceItem("str", "String")
        str_list_type = ChoiceItem("[str]", "List of Strings (comma-separated)")
        int_type = ChoiceItem("int", "Integer")
        bool_type = ChoiceItem("bool", "Boolean")
        float_type = ChoiceItem("float", "Float")
        quantity_type = ChoiceItem("quantity", "Quantity")

    # These are the hardcoded db lookups for fixed block attributes
    # (These are hardcoded for security reasons)
    BLOCK_LOOKUPS = {
        BlockAttribute.name: "name",
        BlockAttribute.part_number: "manufacturer_parts__part_number",
        BlockAttribute.manufacturer: "manufacturer_parts__manufacturer__name",
    }

    BLOCK_VALUE_LOOKUPS = {
        BlockAttribute.name: lambda block: [block.name],
        BlockAttribute.part_number: part_number_values,
        BlockAttribute.manufacturer: manufacturer_values,
    }

    def get_values(self, block):
        if self.is_direct:
            yield from self.BLOCK_VALUE_LOOKUPS[self.block_attribute](block)
        if self.is_block:
            attribute_value = block.attributes.get(self.name)
            if attribute_value is not None:
                yield attribute_value

        for interface_attributes in block.interface_attributes_sets.all():
            value = interface_attributes.attributes.get(self.name)
            if value is not None:
                yield value

    name = SmallTextField()
    block_attribute = SmallTextField(
        blank=True, choices=BlockAttribute.choices, default=""
    )
    datatype = SmallTextField(choices=DataType.choices)
    unit = SmallTextField(blank=True, default="")
    unit_description = SmallTextField(blank=True, default="")
    choices = postgres_fields.ArrayField(SmallTextField(), blank=True, default=list)
    is_required = models.BooleanField(default=False)
    is_range = models.BooleanField(default=False)

    # Attributes can be defined either on a category or an interface type
    category = models.ForeignKey(
        "db.Category",
        related_name="attributes",
        blank=True,
        null=True,
        on_delete=models.CASCADE,
    )
    interface_type = models.ForeignKey(
        "db.InterfaceType",
        related_name="attributes",
        blank=True,
        null=True,
        on_delete=models.CASCADE,
    )

    def __str__(self):
        return self.name

    @property
    def type(self):
        if self.block_attribute:
            return self.Type.DIRECT
        if self.category_id:
            return self.Type.BLOCK
        if self.interface_type_id:
            return self.Type.INTERFACE

        raise RuntimeError(
            "Attribute definition must have a direct attribute, category or interface type"
        )

    @property
    def is_direct(self):
        return self.type is self.Type.DIRECT

    @property
    def is_block(self):
        return self.type is self.Type.BLOCK

    @property
    def is_interface(self):
        return self.type is self.Type.INTERFACE

    def clean(self):
        # Ensure that one, and only one, of category and interface_type are set
        if (
            not self.category_id
            and not self.interface_type_id
            and not self.block_attribute
        ):
            raise ValidationError(
                "Please select a category or an interface type (except for direct attributes)"
            )
        elif self.category_id and self.interface_type_id:
            raise ValidationError(
                "Please select a category or an interface type, not both!"
            )
        elif self.block_attribute and (self.interface_type_id or self.category_id):
            raise ValidationError(
                "Direct block attributes should have neither a category nor interface type."
            )

        # Only a subset of options is supported for direct block attributes
        if self.is_direct:
            if self.datatype == self.DataType.quantity_type:
                raise ValidationError(
                    {
                        "datatype": "Direct block attributes do not support quantities as a datatype"
                    }
                )
            if self.is_range:
                raise ValidationError(
                    {"is_range": "Direct block attributes do not support ranges."}
                )

        if not self.pk or self._state.adding:
            has_changed_to_required = self.is_required
        else:
            old_instance = AttributeDefinition.objects.get(pk=self.pk)
            has_changed_to_required = not old_instance.is_required and self.is_required

        # If this field has gone from not required to required, we should only allow it
        # if all instances within parts or interfaces are filled it out.
        if has_changed_to_required:
            from cm.db.attribute_field import AttributeField
            from cm.db.models import Block

            if self.is_direct:
                # We could do some validation for is_required, but for now we just trust that the attributes
                # are set up in accordance with the model fields.
                invalid_object_count = 0
            elif self.category:
                matching_categories = self.category.get_descendants(include_self=True)
                # FIXME: this need a second case for direct filters

                invalid_object_count = Block.objects.filter(
                    AttributeField.lookup_missing(self.name),
                    categories__in=matching_categories,
                ).count()
                object_name = "parts"
            else:
                invalid_object_count = self.interface_type.attributes_sets.filter(
                    AttributeField.lookup_missing(self.name)
                ).count()
                object_name = "interfaces"

            if invalid_object_count:
                raise ValidationError(
                    {
                        "is_required": (
                            f"Cannot make {self.name} required - {invalid_object_count} "
                            f"{object_name} are missing this attribute"
                        )
                    }
                )

        if self.datatype == self.DataType.quantity_type:
            if not self.unit:
                raise ValidationError({"unit": "A unit is required for quantities!"})

            try:
                parse_unit(self.unit)
            except UndefinedUnitError:
                raise ValidationError({"unit": "Invalid unit specified"})

    @classmethod
    def _values_iter(cls, **kwargs):
        """Returns an iterator over all attribute values that match a given lookup.

        This is used to find values for attributes that currently exist in the database.

        Example:
            AttributeDefinition._values_iter({'name__startswith': 'Banana'})
            will return all values of any attribute whose name starts with "Banana"
        """
        from cm.db.query import AttributeQuery

        attribute_filter_queries = [
            AttributeQuery(
                name=attribute_definition.name,
                attribute_definition=attribute_definition,
                operator=AttributeQuery.Operator.ISNULL,
                value=False,
                exclude=False,
            )
            for attribute_definition in cls.objects.filter(**kwargs)
        ]

        for query in attribute_filter_queries:
            for values in (
                query.as_queryset()
                .filter(manual_only=False)
                .order_by(query.field_filter)
                .distinct()
                .values_list(query.field_filter, flat=True)
            ):
                for value in values if isinstance(values, list) else [values]:
                    yield value

    @classmethod
    def values(cls, **kwargs):
        return sorted(cls._values_iter(**kwargs))


class DirectAttributeDefinitionManager(Manager):
    def get_queryset(self):
        qs = super().get_queryset()
        return qs.exclude(block_attribute=BlockAttribute.none)


class DirectAttributeDefinition(AttributeDefinition):
    """Proxy model for direct block attribute definitions."""

    class Meta:
        proxy = True

    objects = DirectAttributeDefinitionManager()
