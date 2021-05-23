from django.db import models

from cm.db.constants import BusSharing, PinType
from cm.db.fields import SmallTextField

from .base_model import BaseModel
from .interface_type import InterfaceType


class InterfacePin(BaseModel):
    """This class describes a definition of a pin that is required for an interface to function."""

    class Meta:
        ordering = ("interface_type", "reference", "id")
        unique_together = ("interface_type", "reference")

    interface_type = models.ForeignKey(
        InterfaceType, related_name="pins", on_delete=models.CASCADE
    )
    reference = SmallTextField(verbose_name="pin reference")
    pin_type = models.CharField(max_length=10, choices=PinType.choices)
    description = SmallTextField(blank=True)
    is_required = models.BooleanField(default=True)
    multiple_use = models.BooleanField(
        default=False,
        help_text=(
            "Indicates whether this interface pin can be used "
            "multiple times in a single bus, i.e. the chip select "
            "pin of a SPI can be used multiple times "
        ),
    )
    sharing = SmallTextField(
        help_text="Determines if and how pins of this type can be shared",
        default=BusSharing.point_to_point,
        choices=BusSharing.choices,
    )
    create_automatically = models.BooleanField(
        default=False,
        help_text=(
            "In a bulk import, automatically create an assignment (to all matching pins) if no assignment is "
            "explicitly given."
        ),
    )
    parent_pins = models.ManyToManyField(
        "self",
        related_name="child_pins",
        symmetrical=False,
        blank=True,
        help_text="First assign a parent to the interface type, then select how to map each interface pin.",
    )
    compatible_pins = models.ManyToManyField(
        "self",
        symmetrical=True,
        help_text="First select which interface types this type is compatible with in general, then specify each pin.",
        blank=True,
    )

    def __str__(self):
        return f"{self.interface_type} - {self.reference}"

    @property
    def is_shared(self):
        return self.sharing == BusSharing.shared
