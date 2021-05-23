from django.db import models

from cm.db.fields import SmallTextField

from .base_model import BaseModel
from .manufacturer import Manufacturer
from .part import Part


class ManufacturerPart(BaseModel):
    """Manufacturer-specific details about a part."""

    class Meta:
        unique_together = ("manufacturer", "part_number")
        ordering = ("manufacturer", "part_number", "id")

    part = models.ForeignKey(
        Part, related_name="manufacturer_parts", on_delete=models.CASCADE
    )
    manufacturer = models.ForeignKey(Manufacturer, on_delete=models.PROTECT)

    part_number = SmallTextField()

    def __str__(self):
        return f"{self.part_number} ({self.manufacturer})"
