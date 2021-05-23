import re
from typing import Dict, cast

from colorfield.fields import ColorField
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.text import slugify

from cm.db.constants import InterfaceTypeFunction
from cm.db.fields import SmallTextField
from cm.db.models import AttributeDefinition

from .base_model import BaseModel

SUPPORTED_BULK_VARIABLES = [
    # These are the names groups that can be used in the bulk_input_pattern regular expression
    "name",
    "pin",
    "group",
    "channel",
]
SUPPORTED_INTERFACE_BULK_VARIABLES = [
    # These are the names groups that can be used in the interface_bulk_input_pattern regular expression
    "type",
    "index",
]


class InterfaceType(BaseModel):
    class Meta:
        ordering = ("name", "id")

    name = SmallTextField(unique=True)
    label = SmallTextField(
        help_text="The prefix used in interfaces of this type (GND, SPI, etc)"
    )
    description = models.TextField(blank=True)
    family = models.ForeignKey(
        "db.InterfaceFamily",
        related_name="interface_types",
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
    )
    interface_bulk_input_pattern = SmallTextField(
        blank=True,
        help_text="Regular expression for interface bulk input, e.g. SPI0_M.",
    )
    bulk_input_pattern = SmallTextField(
        blank=True, help_text="Regular expression for pin bulk input, e.g. SPI0_M_MISO"
    )
    allow_child_interfaces = models.BooleanField(
        default=False,
        help_text=(
            "Other interfaces can use interfaces of this type as a parent. "
            "(Used for SERCOMs, etc)"
        ),
    )
    parents = models.ManyToManyField(
        "self", related_name="children", symmetrical=False, blank=True
    )
    function = SmallTextField(
        choices=InterfaceTypeFunction.choices,
        help_text="Specialised function of this interface type",
        default=InterfaceTypeFunction.none,
    )
    can_be_required = models.BooleanField(
        default=True,
        help_text=(
            "Is it possible for interfaces of this type to be required? For example, a SPI master interface "
            "can never be required, but a UART interface might be required or not."
        ),
    )
    can_be_specialised = models.BooleanField(
        default=False,
        help_text=(
            "A generic interface type that can be specialised as one or more other interface types. For example, a "
            "connector could be specialised to consist of SPI, I²C, Digital, etc."
        ),
    )

    compatible_interface_types = models.ManyToManyField(
        "self",
        symmetrical=True,
        blank=True,
        help_text=(
            "What other interface types can this type connect to? Should only be specified on child interfaces."
        ),
        limit_choices_to={"children__isnull": True},
    )

    text_color = ColorField(default="#000000")
    background_color = ColorField(default="#FFFFFF")

    def __str__(self):
        return self.name

    def full_name(self):
        if self.family:
            return f"{self.name} ({self.get_family_label()})"
        return self.name

    @property
    def slug(self):
        return slugify(self.name)

    def clean(self):
        if self.bulk_input_pattern:
            bulk_input_expression = re.compile(self.bulk_input_pattern)
            # Check that only supported named groups are used
            invalid_groups = [
                group_name
                for group_name in bulk_input_expression.groupindex.keys()
                if group_name not in SUPPORTED_BULK_VARIABLES
            ]
            if invalid_groups:
                raise ValidationError(
                    {
                        "bulk_input_pattern": (
                            f"Invalid groups {', '.join(invalid_groups)}. "
                            f"Supported groups are {', '.join(SUPPORTED_BULK_VARIABLES)}."
                        )
                    }
                )

        if self.interface_bulk_input_pattern:
            bulk_input_expression = re.compile(self.interface_bulk_input_pattern)
            groups = bulk_input_expression.groupindex.keys()
            # Check that only supported named groups are used
            invalid_groups = [
                group_name
                for group_name in groups
                if group_name not in SUPPORTED_INTERFACE_BULK_VARIABLES
            ]
            if invalid_groups:
                raise ValidationError(
                    {
                        "interface_bulk_input_pattern": (
                            f"Invalid groups {', '.join(invalid_groups)}. "
                            f"Supported groups are {', '.join(SUPPORTED_INTERFACE_BULK_VARIABLES)}."
                        )
                    }
                )
            missing_groups = [
                group_name
                for group_name in SUPPORTED_INTERFACE_BULK_VARIABLES
                if group_name not in groups
            ]
            if missing_groups:
                raise ValidationError(
                    {
                        "interface_bulk_input_pattern": f'Missing regex groups {", ".join(missing_groups)}'
                    }
                )

    def interface_index(self, interface):
        if not self.interface_bulk_input_pattern:
            raise KeyError(
                "Can't get index for interface without interface input pattern!"
            )
        m = re.fullmatch(self.interface_bulk_input_pattern, interface.name)
        if not m:
            raise KeyError(
                f"Name of interface {interface} doesn't match its input pattern!"
            )
        return int(m.groupdict()["index"])

    def interface_name(self, interface_index):
        """Create a new interface name for this type, for a given index."""
        if not self.label:
            raise KeyError(f"{self} has no label assigned!")
        return f"{self.label}{interface_index}"

    def highest_index(self, connectivity):
        """Return the highest interface index on this type for a given connectivity."""
        return max(
            [
                self.interface_index(interface)
                for interface in self.interfaces.filter(connectivity_id=connectivity)
            ]
        )

    def next_index(self, connectivity):
        return self.highest_index(connectivity) + 1

    def get_full_attributes(self) -> Dict[str, AttributeDefinition]:
        """Return the attibute definitions for this interface type, indexed by attribute name."""
        return {attribute.name: attribute for attribute in self.attributes.all()}

    def get_family_label(self) -> str:
        return cast(str, self.family.label if self.family_id else self.label)

    def get_ancillaries(self):
        parents_with_ancillaries = self.parents.filter(ancillaries__isnull=False)[:1]
        if not parents_with_ancillaries.exists():
            return self.ancillaries.all()
        return parents_with_ancillaries.first().ancillaries.all()

    def get_ancestors(self, include_self=False):
        """Get all ancestor interface types"""
        ancestors = self.parents.all()
        if include_self:
            return ancestors | InterfaceType.objects.filter(pk=self.pk)
        return ancestors

    def is_child(self, qs, include_self=False):
        """Check if this interface type is in the specified queryset or is a child."""
        return self.get_children(qs, include_self).filter(id=self.id).exists()

    @classmethod
    def get_children(cls, qs, include_self=False):
        """Get all interface types that are "child" (leaf) nodes from a queryset. For any interface types
        that have children, then get their children instead."""
        return cls.get_descendants(qs, include_self).filter(children__isnull=True)

    @classmethod
    def get_descendants(cls, qs, include_self=False):
        """Get all descendant interface types from a QuerySet"""
        descendants = cls.objects.filter(parents__in=qs)
        return qs | descendants if include_self else descendants

    @classmethod
    def validate_parents(cls, parents):
        """Validate a set of interface type parents by checking they all share the same family."""
        if len(set(parent.family for parent in parents)) > 1:
            raise ValueError(
                "Parent interface types must all belong to the same family."
            )
