import re
from copy import copy
from typing import Optional, cast
from uuid import UUID

from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ValidationError
from django.db import models

from cm.db.constants import InterfaceTypeFunction, PinType
from cm.db.fields import SmallTextField

from .base_model import BaseModel
from .connectivity import Connectivity

PIN_ORDERING_FORMAT = (
    r"((?P<prefix_number>\d{1,4})?(?P<letters>[a-zA-Z]{1,4}))?(?P<number>\d{1,4})"
)


def pin_order(pin_number: str) -> str:
    """Ordering function to determine a numeric ordering for string-based pin numbers.

    These numbers can just be integer numbers, but they can also be grid - based, like A0, 1A0 or BB55.

    We always convert them to a left-padded string of grid letters and numbers, to allow stable string sorting.

    Example:
        1 -> 000000000001
        A1 -> 0000000A0001
        1A1 -> 0001000A0001
        ABCD9999 -> 0000ABCD9999
    """

    m = re.fullmatch(PIN_ORDERING_FORMAT, pin_number)
    if not m:
        raise ValidationError(
            f"{pin_number} is not a valid pin number. Supported formats are int numbers or strings "
            "in the format of [0-9]*[A-Z]*[0-9]+, e.g. G17 or ABZG9999"
        )

    # Get the grid coordinates and left-pad them so we can use string comparision to sort the values.
    groups = m.groupdict()
    grid_prefix_number = (groups.get("prefix_number") or "").zfill(4)
    grid_letters = (groups.get("letters") or "").zfill(4)
    grid_number = groups["number"].zfill(4)

    return f"{grid_prefix_number}{grid_letters}{grid_number}"


class Pin(BaseModel):
    """The pin class describes a logical pin on a component."""

    class Meta:
        ordering = ("_number_order", "name", "id")
        unique_together = ("number", "connectivity")

    name = SmallTextField()
    number = SmallTextField(validators=[pin_order])
    identifiers = ArrayField(SmallTextField())  # name and number, for easier lookups
    _number_order = models.CharField(max_length=12)

    connectivity = models.ForeignKey(
        Connectivity,
        related_name="pins",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )

    pin_type = models.CharField(max_length=10, choices=PinType.choices, blank=True)

    voltage_reference = models.ForeignKey(
        "db.Interface",
        limit_choices_to={"interface_type__function": InterfaceTypeFunction.power},
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    idn = id

   
    @property
    def aaa(self) -> bool:
        return (True)


    def __str__(self):
        return f"{self.name} (#{self.number})"

    def voltage_reference_pin(self) -> Optional["Pin"]:
        """Return an (arbitrary) power pin from self.voltage_reference."""
        if self.pin_type == PinType.power:
            return None
        if not self.voltage_reference_id:
            return None
        return cast(
            Optional[Pin],
            Pin.objects.filter(assignments__interface=self.voltage_reference).first(),
        )

    def gnd_reference_pin(self) -> Optional["Pin"]:
        """Return an (arbitrary) gnd pin from self.voltage_reference."""
        if self.pin_type == PinType.gnd:
            return None
        if self.pin_type == PinType.power:
            from cm.db.models.interface import Interface

            power_interface = Interface.objects.filter(
                pin_assignments__pins=self
            ).first()
            if not power_interface:
                return None

            return cast(
                Optional[Pin],
                Pin.objects.filter(
                    voltage_reference=power_interface, pin_type=PinType.gnd
                ).first(),
            )
        if not self.voltage_reference_id:
            return None
        return cast(
            Optional[Pin],
            Pin.objects.filter(
                voltage_reference=self.voltage_reference, pin_type=PinType.gnd
            ).first(),
        )

    def duplicate(
        self, connectivity_id: UUID, voltage_reference_id: Optional[UUID]
    ) -> "Pin":
        """Save a copy of this pin to the database.

        Requires passing in the id of the connectivity that the copy should be assigned to.
        """
        duplicate_instance = copy(self)
        duplicate_instance.pk = None
        duplicate_instance.connectivity_id = connectivity_id
        duplicate_instance.voltage_reference_id = voltage_reference_id
        duplicate_instance.save(skip_resaving_assignments=True)
        return duplicate_instance

    def save(self, *args, skip_resaving_assignments=False, **kwargs):
        self._number_order = pin_order(self.number)
        self.identifiers = [self.name, self.number]

        super().save(*args, **kwargs)
