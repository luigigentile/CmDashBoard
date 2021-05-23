import re

from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ValidationError
from django.db import models
from djchoices import ChoiceItem, DjangoChoices

from cm.db.fields import SmallTextField
from cm.db.models.pin import Pin

from .base_model import BaseModel
from .interface import Interface
from .interface_pin import InterfacePin

PIN_IDENTIFIER_WILDCARD_FORMAT = r"\*"
FIELD_LOOKUP_FORMAT = r"(?P<field>[a-z_]+) ?(?P<negate>!)? ?(?P<operator>=|~=|>|<|<=|>=) ?(?P<value>[a-zA-Z0-9_\-\.]+)"
PIN_IDENTIFIER_LOOKUP_FORMAT = r"\[(?:" + FIELD_LOOKUP_FORMAT + r",?)+\]"
PIN_IDENTIFIER_LIST_FORMAT = r"(?:\d*[a-zA-Z]*\d+ ?, ?)*\d*[a-zA-Z]*\d+"
PIN_IDENTIFIER_DEPENDENT_LIST_FORMAT = "{" + PIN_IDENTIFIER_LIST_FORMAT + "}"

PIN_IDENTIFIER_HELP_TEXT = """Identifier string used to find the pins that should be assigned. This can be
- a simple number (A37)
- a list of pin numbers (A37,A55)
- a list of pin numbers that have to be picked together with other pins ({A37,A55})
- a wildcard indicating all pins of matching type (*)
- a lookup checking pin parameters ([type=Digital, name~=SPI, number!=5])

Supported operators on the lookups are
= exact match
>, >=, <, <= larger/smaller than (or equal to)
~= contains (case-independent substring match)

You can also invert the matches by adding a ! before, e.g.
- name!~=dig_ -> all pins whose name doesn't contain the string dig_
- type!=Digital -> all non-digital pins
"""


def validate_pin_identifiers(value):
    """Validates that a field value represents a correct pin identifier string.

    These identifiers can identify one or more pins, as well as indicate if the pins are independent or dependent
    on other selected pins. """

    matches_wildcard = re.fullmatch(PIN_IDENTIFIER_WILDCARD_FORMAT, value)
    matches_lookup = re.fullmatch(PIN_IDENTIFIER_LOOKUP_FORMAT, value)
    matches_independent_list = re.fullmatch(PIN_IDENTIFIER_LIST_FORMAT, value)
    matches_dependent_list = re.fullmatch(PIN_IDENTIFIER_DEPENDENT_LIST_FORMAT, value)
    matches = any(
        [
            matches_wildcard,
            matches_lookup,
            matches_independent_list,
            matches_dependent_list,
        ]
    )

    # Do additional validation for lookups
    if matches_lookup:
        raw_lookups = value[1:-1].split(
            ","
        )  # remove the brackets and split the statements
        for raw_lookup in raw_lookups:
            match_groups = matches_lookup.groupdict()
            raw_field, operator, value = (
                match_groups["field"],
                match_groups["operator"],
                match_groups["value"],
            )

            try:
                PinAssignment.PIN_FIELDS[raw_field]
            except KeyError:
                allowed_fields = PinAssignment.PIN_FIELDS.keys()
                raise ValidationError(
                    f"Invalid pin field {raw_field} used in lookup {raw_lookup}! "
                    f'Allowed fields are {", ".join(allowed_fields)}.'
                )

            try:
                PinAssignment.PIN_LOOKUPS[operator]
            except KeyError:
                allowed_operators = PinAssignment.PIN_LOOKUPS.keys()
                raise ValidationError(
                    f"Invalid pin operator {operator} used in lookup {raw_lookup}! "
                    f"Allowed operators are {allowed_operators}"
                )

    if matches:
        return True

    raise ValidationError(
        "Couldn't parse pin identifiers! Accepted formats are "
        "`*` (everything), `[lookup=value,..]`, `{1,2,4,5}` and `1,2,3,4`"
    )


class PinAssignment(BaseModel):
    """A pin assignment determines which pins (of a connectivity or parent interface) are assigned to which interfaces.

    Each interface pin can be assigned to
        - one parent pin assignment OR
        - a number of possible physical pins.
    """

    PIN_FIELDS = {
        "type": "pin_type",  # Pin type string lookup
        "name": "name",  # Pin name
        "number": "number",  # Pin number
    }
    PIN_LOOKUPS = {
        "<": "lt",
        ">": "gt",
        "<=": "lte",
        ">=": "gte",
        "=": "iexact",
        "~=": "icontains",
    }

    class PinIdentifierType(DjangoChoices):
        none = ChoiceItem("none", "None")
        wildcard = ChoiceItem("wildcard", "All Pins")
        independent = ChoiceItem("independent", "Independent Pins")
        dependent = ChoiceItem("dependent", "Dependent Pins")
        by_attributes = ChoiceItem("by_attributes", "By Attributes")

    class Meta:
        ordering = ("interface__interface_type__name", "id")

    interface = models.ForeignKey(
        Interface, related_name="pin_assignments", on_delete=models.CASCADE
    )
    interface_pin = models.ForeignKey(
        InterfacePin, related_name="pin_assignments", on_delete=models.CASCADE
    )

    # Index of the interface channel used.
    channel = models.PositiveIntegerField(default=0)

    # In addition to an interface being able to have a parent interface,
    # a pin assignment can also specify a specific interface pin of that parent interface.
    # This restricts the possible pins to the intersection of the pin assignment and the parent's pin assignments.
    parent_interface_pin = models.ForeignKey(
        InterfacePin,
        related_name="children",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
    )

    pin_identifiers = SmallTextField(
        validators=[validate_pin_identifiers],
        blank=True,
        default="",
        help_text=PIN_IDENTIFIER_HELP_TEXT,
    )
    pin_identifiers_type = SmallTextField(choices=PinIdentifierType.choices)
    # This is a cache of the assigned pins, saved in the db because calculating this for all pins can get expensive.
    # Note: don't ever use this for anything crucial, as it's not 100% reliable!
    _cached_pin_ids = ArrayField(models.UUIDField(), blank=True, default=list)

    pins = models.ManyToManyField(Pin, related_name="assignments", blank=True)

    def _get_pin_identifiers_type(self):
        """Return the type of the pin identifiers used in this assignment."""
        if not self.pin_identifiers:
            return self.PinIdentifierType.none
        if self.pin_identifiers == "*":
            return self.PinIdentifierType.wildcard
        if "[" in self.pin_identifiers:
            return self.PinIdentifierType.by_attributes
        if "{" in self.pin_identifiers:
            return self.PinIdentifierType.dependent
        return self.PinIdentifierType.independent

    def __str__(self):
        if self.pin_identifiers:
            assigned_to = f"pins {self.pin_identifiers}"
        elif self.parent_interface_pin_id:
            assigned_to = self.parent_interface_pin
        else:
            assigned_to = "-"

        return f"{self.interface.name} {self.interface_pin.reference} on {assigned_to}"

    @classmethod
    def get_pin_lookups(cls, interface_pin, pin_identifiers):
        """Get the filters to determine the related pins according to pin_identifiers.
        Returns a tuple of (filter_arguments, exclude_arguments)
        """
        if not pin_identifiers:
            return None

        if re.fullmatch(PIN_IDENTIFIER_WILDCARD_FORMAT, pin_identifiers):
            # Use all available pins. We still filter down to the correct pin type.
            # This is simply a shortcut for [type=<pin_type>]
            return {"pin_type": interface_pin.pin_type}, {}

        if re.fullmatch(PIN_IDENTIFIER_LOOKUP_FORMAT, pin_identifiers):
            # Filtering for attributes, e.g. [type=DIG,name~=GPIO]
            filter_lookups = {}
            exclude_lookups = {}
            raw_lookups = pin_identifiers[1:-1].split(
                ","
            )  # remove the brackets and split the statements
            for raw_lookup in raw_lookups:
                m = re.fullmatch(FIELD_LOOKUP_FORMAT, raw_lookup)
                if not m:
                    raise RuntimeError(f"Found invalid pin lookup {raw_lookup}!")
                match_groups = m.groupdict()
                raw_field, operator, value = (
                    match_groups["field"],
                    match_groups["operator"],
                    match_groups["value"],
                )

                field = cls.PIN_FIELDS[raw_field]
                lookup = cls.PIN_LOOKUPS[operator]

                field_name_with_lookup = f"{field}__{lookup}"
                if match_groups["negate"]:
                    exclude_lookups[field_name_with_lookup] = value
                else:
                    filter_lookups[f"{field}__{lookup}"] = value
            return filter_lookups, exclude_lookups
        if re.fullmatch(PIN_IDENTIFIER_LIST_FORMAT, pin_identifiers) or re.fullmatch(
            PIN_IDENTIFIER_DEPENDENT_LIST_FORMAT, pin_identifiers
        ):
            # Remove the dependent pin curly braces, if any. (We don't care about them here.)
            raw_lookup = pin_identifiers.replace("{", "").replace("}", "")
            identifiers = [s.strip() for s in raw_lookup.split(",")]

            return {"identifiers__overlap": identifiers}, {}

        raise RuntimeError(f"Unknown filter format {pin_identifiers}!")

    def _query_pins(
        self,
        filter_lookups,
        exclude_lookups,
        parent_filter_lookups,
        parent_exclude_lookups,
    ):
        qs = Pin.objects.filter(connectivity=self.interface.connectivity)
        if filter_lookups:
            qs = qs.filter(**filter_lookups)
        if exclude_lookups:
            qs = qs.exclude(**exclude_lookups)
        if parent_filter_lookups:
            qs = qs.filter(**parent_filter_lookups)
        if parent_exclude_lookups:
            qs = qs.exclude(**parent_exclude_lookups)

        return qs

    def calculate_assigned_pins(self):
        """Uses self.pin_identifiers to calculate the assigned pins."""

        lookups = self.get_pin_lookups(self.interface_pin, self.pin_identifiers)
        if lookups is None:
            filter_lookups = exclude_lookups = None
        else:
            filter_lookups, exclude_lookups = lookups

        if (
            self.interface.parent_id is not None
            and self.parent_interface_pin_id is not None
        ):
            # This assignment also has a parent assignment - we need to return the subset of the child and parent pins.
            parent_assignment = PinAssignment.objects.get(
                interface_pin=self.parent_interface_pin, interface=self.interface.parent
            )

            parent_lookups = PinAssignment.get_pin_lookups(
                self.parent_interface_pin, parent_assignment.pin_identifiers
            )
            if not parent_lookups:
                raise RuntimeError(
                    f"Parent assignment {parent_assignment} of assignment {self} has no pin lookups! "
                    "That should never happen."
                )
            parent_filter_lookups, parent_exclude_lookups = parent_lookups
        else:
            parent_filter_lookups = parent_exclude_lookups = None

        # Special case of no lookups whatsoever means no pins are assigned, rather than all pins
        if not any(
            [
                filter_lookups,
                exclude_lookups,
                parent_filter_lookups,
                parent_filter_lookups,
            ]
        ):
            return Pin.objects.none()

        return self._query_pins(
            filter_lookups,
            exclude_lookups,
            parent_filter_lookups,
            parent_exclude_lookups,
        )

    def get_child_assignments(self):
        """Helper function to get any child assignments that correspond to this assignment."""

        return PinAssignment.objects.filter(
            interface__parent=self.interface, parent_interface_pin=self.interface_pin
        )

    @classmethod
    def cross_validate_dependent_pins(cls, assignments):
        """Check a list of assignments to make sure that their dependent pin identifiers are valid together.

        Currently that just means checking that they all have the same length. """
        if not assignments:
            return

        # Pick any of the assignments as an example, we're only checking that there is only a single count of pins
        num_pins = set(
            [
                len(assignment.pin_identifiers.split(","))
                for assignment in assignments
                if assignment._get_pin_identifiers_type()
                == PinAssignment.PinIdentifierType.dependent
            ]
        )
        if len(num_pins) > 1:
            raise ValidationError(
                {
                    "pin_identifiers": (
                        "All mutually dependent pin assignments (using {}) have to have the same "
                        "number of assigned pins!"
                    )
                }
            )

    def clean(self):
        if self.interface_id is None:
            return

        has_parent_interface = self.interface.parent_id is not None
        has_pin = bool(self.pin_identifiers)

        if not has_parent_interface and not has_pin:
            raise ValidationError(
                {
                    "pin_identifiers": "Please specify pin_identifiers for ungrouped interfaces!"
                }
            )

        # We need to validate that any assignment using mutually dependent pins is compatible with other existing ones.
        if self._get_pin_identifiers_type() == self.PinIdentifierType.dependent:
            # Get any other assignments using dependent pins
            other_dependent_assignments = PinAssignment.objects.filter(
                interface=self.interface,
                pin_identifiers_type=self.PinIdentifierType.dependent,
            )
            if self.pk:
                other_dependent_assignments = other_dependent_assignments.exclude(
                    pk=self.pk
                )
            self.cross_validate_dependent_pins(
                [self] + list(other_dependent_assignments)
            )

        # Validate that the chosen channel is valid
        if self.channel >= self.interface.channels:
            raise ValidationError(
                {
                    "channel": (
                        f"Cannot use channel index {self.channel} on "
                        f"interface with {self.interface.channels} channels!"
                    )
                }
            )

    def save(self, *args, **kwargs):
        # Denormalize the type of the pin identifiers used in the database
        # This is calculated from the pin identifiers value and just makes it easier to query for assignments.
        self.pin_identifiers_type = self._get_pin_identifiers_type()

        super().save(*args, **kwargs)
        # Update the assigned pins - has to happen after super().save to make sure self exists!
        self.pins.set(self.calculate_assigned_pins())

    def duplicate(self, interface_id):
        new_assignment = PinAssignment(
            interface_id=interface_id,
            parent_interface_pin=self.parent_interface_pin,
            interface_pin=self.interface_pin,
            pin_identifiers=self.pin_identifiers,
        )
        new_assignment.save()  # Make sure the assigned pins get calculated from the pin identifiers

        return new_assignment
