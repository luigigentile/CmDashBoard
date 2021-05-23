from django.core.exceptions import ValidationError
from django.db import models

from .base_model import BaseModel


class PinUse(BaseModel):
    class Meta:
        unique_together = (
            ("subcircuit", "block_filter", "interface", "pin"),  # one pin use per pin
            (
                "subcircuit",
                "block_filter",
                "interface",
                "interface_pin",
            ),  # one pin use per interface pin
        )

    """A pin use allows a user to pre-define which pins various interfaces of a subcircuit should use."""

    subcircuit = models.ForeignKey(
        "db.SubCircuit", on_delete=models.CASCADE, related_name="pin_uses"
    )

    block_filter = models.ForeignKey(
        "db.BlockFilter", on_delete=models.CASCADE, related_name="pin_uses",
    )

    interface = models.ForeignKey(
        "db.Interface", related_name="pin_uses", on_delete=models.CASCADE,
    )

    interface_pin = models.ForeignKey(
        "db.InterfacePin", related_name="pin_uses", on_delete=models.CASCADE,
    )

    pin = models.ForeignKey("db.Pin", on_delete=models.CASCADE, null=True, blank=True)

    def clean(self):
        if self.subcircuit_id and self.block_filter_id:
            if self.block_filter.subcircuit_id != self.subcircuit_id:
                raise ValidationError(
                    "Block_filter of Pin Use must be part of its subcircuit!"
                )

        if (
            self.block_filter_id
            and self.interface_id
            and self.block_filter.connectivity_id
        ):
            if self.interface.connectivity_id != self.block_filter.connectivity_id:
                raise ValidationError(
                    "Interface of Pin Use must be part of its connectivity!"
                )

        if self.interface_id and self.interface_pin_id:
            if self.interface_pin.interface_type != self.interface.interface_type:
                raise ValidationError(
                    "Interface pin of Pin Use must match its interface type!"
                )

        if self.pin_id and self.block_filter_id and self.block_filter.connectivity_id:
            if self.pin.connectivity_id != self.block_filter.connectivity_id:
                raise ValidationError("Pin of Pin Use must match its connectivity!")
