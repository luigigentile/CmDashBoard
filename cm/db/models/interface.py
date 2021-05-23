import re
from collections import defaultdict
from copy import copy
from typing import Dict

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.db.models.query import QuerySet

from cm.db.constants import InterfaceFunction
from cm.db.fields import SmallTextField
from cm.db.models import ConnectionRule

from .base_model import BaseModel
from .connectivity import Connectivity
from .interface_type import InterfaceType
from .pin import Pin


class SerializableMinValueValidator(MinValueValidator):
    def __str__(self) -> str:
        return f"MinValuevalidator({self.limit_value})"


class Interface(BaseModel):
    class Meta:
        ordering = ("name", "id")
        unique_together = [
            ("name", "connectivity", "parent"),
        ]

    name = SmallTextField()
    connectivity = models.ForeignKey(
        Connectivity, related_name="interfaces", on_delete=models.CASCADE
    )
    interface_type = models.ForeignKey(
        InterfaceType, related_name="interfaces", on_delete=models.PROTECT
    )

    # Functional fields (what is this interface used for)
    function = SmallTextField(
        choices=InterfaceFunction.choices,
        help_text="Specialised function of this interface",
        blank=True,
        null=True,
        default=InterfaceFunction.inherit,
    )
    is_required = models.BooleanField(
        help_text='Only available if the interface type has "can_be_required" set to true.',
        default=False,
    )
    channels = models.PositiveIntegerField("Number of channels", default=1)

    parent = models.ForeignKey(
        "self",
        related_name="children",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        help_text="Parent interface for grouped interfaces",
        limit_choices_to={"interface_type__allow_child_interfaces": True},
    )

    max_child_interfaces = models.PositiveIntegerField(
        default=1,
        help_text=(
            "How many child interfaces of this interface can be used "
            "in parallel? (Only applies to parent interfaces)"
        ),
        validators=[SerializableMinValueValidator(1)],
    )

    def __str__(self):
        return f"{self.name} ({self.interface_type})"

    def duplicate(self, connectivity_id, parent_id=None):
        if self.parent_id and parent_id is None:
            raise RuntimeError(
                "No parent_id passed to interface.duplicate of a child interface!"
            )

        duplicate_instance = copy(self)
        duplicate_instance.pk = None
        duplicate_instance.connectivity_id = connectivity_id
        duplicate_instance.parent_id = parent_id
        duplicate_instance.save()
        return duplicate_instance

    @property
    def interface_index(self):
        if not self.interface_type.interface_bulk_input_pattern:
            raise KeyError(
                "Can't get index for interface without interface input pattern!"
            )
        m = re.fullmatch(self.interface_type.interface_bulk_input_pattern, self.name)
        if not m:
            raise KeyError(f"Name of interface {self} doesn't match its input pattern!")
        return m.groupdict()["index"]

    def validate(self):
        """Check if this interface and its assignments are valid.

        Returns a tuple of(is_valid, errors, warnings). """
        interface_assignments = self.pin_assignments.all()
        interface_pins = self.interface_type.pins.all()
        errors = []
        warnings = []

        assignment_counts: Dict[str, int] = defaultdict(int)
        for assignment in interface_assignments:
            assignment_counts[assignment.interface_pin] += 1

        for interface_pin in interface_pins:
            count = assignment_counts[interface_pin]
            if not count and interface_pin.is_required:
                errors.append(
                    f"Required Interface pin {interface_pin.reference} not used!"
                )
            if count > 1:
                warnings.append(
                    f"Interface pin {interface_pin.reference} used more than once!"
                )

        return not bool(errors), errors, warnings

    @property
    def is_multichannel(self):
        return self.channels > 1

    def get_pins(self) -> QuerySet:
        """Get all pins this interface is assigned to."""

        return Pin.objects.filter(assignments__in=self.pin_assignments.all())

    def get_primary_connection_rule(self):
        """Get the top-priority connection rule for this interface."""
        return self.get_connection_rules().first()

    def get_connection_rules(self):
        """Get the connection rules for this interface, which can be defined on the interface or its type."""
        return ConnectionRule.objects.filter(
            Q(interface=self) | Q(interface_type=self.interface_type)
        )

    @staticmethod
    def function_lookup(function: InterfaceFunction) -> Q:
        """Q object for filtering interfaces with a given function.

        This is required because an interface's function can come either from the interface itself, or its
        interface type.
        """
        return Q(function=function) | (
            Q(function=InterfaceFunction.inherit) & Q(interface_type__function=function)
        )

    def get_function(self):
        """An interface's function can be defined on it, or on the interface type."""
        return (
            self.function
            if self.function != InterfaceFunction.inherit
            else self.interface_type.function
        )

    def clean(self):
        interface_duplicates = Interface.objects.filter(
            connectivity=self.connectivity, name=self.name, parent=self.parent,
        )
        if self.pk is not None:
            interface_duplicates = interface_duplicates.exclude(pk=self.pk)
        if interface_duplicates.exists():
            raise ValidationError(
                f"Interface with this name and parent already exists on {self.connectivity.name}"
            )

        if self.is_required and not self.interface_type.can_be_required:
            raise ValidationError(
                {
                    "is_required": f"Interfaces of type {self.interface_type} cannot be required!"
                }
            )

    def get_child_interfaces_on_pin(self, pin):
        all_children = self.children.all()
        return [
            child
            for child in all_children
            if child.get_pins().filter(id=pin.id).exists()
        ]

    def get_ancillaries(self, subcircuit_id=None):
        """Get all ancillaries that are on this interface or its interface type."""
        ancillaries = self.ancillaries.all() | self.interface_type.get_ancillaries()
        if subcircuit_id:
            ancillaries = ancillaries.filter(
                Q(subcircuit_id=subcircuit_id) | Q(subcircuit_id__isnull=True)
            )
        else:
            ancillaries = ancillaries.filter(subcircuit_id__isnull=True)
        return ancillaries.distinct()
