from django.core.exceptions import ValidationError
from django.db import models

from cm.db.models.base_model import BaseModel


class InterfaceAdapter(BaseModel):
    """Adapter or buses between interfaces that are usually incompatible or belong to different families.

    This allows the user to specify how the incompatibility of the interfaces should be resolved,
    by mapping the incompatible interfaces to a compatible one.
    """

    def __str__(self) -> str:
        from_side = (
            f"({self.original_from} as {self.adapted_from})"
            if self.adapted_from
            else f"{self.original_from}"
        )
        to_side = (
            f"({self.original_to} as {self.adapted_to})"
            if self.adapted_to
            else f"{self.original_to}"
        )

        return f"{from_side} ➡ {to_side}"

    bus_fragment = models.ForeignKey(
        "db.BusFragment", related_name="interface_adapters", on_delete=models.CASCADE
    )

    # queryset limited to the "real" interface pins that match the respective bus_fragment.x_interface_type
    original_from = models.ForeignKey(
        "db.InterfacePin",
        related_name="adapters_original_from",
        on_delete=models.CASCADE,
    )
    adapted_from = models.ForeignKey(
        "db.InterfacePin",
        null=True,
        blank=True,
        related_name="adapters_adapted_from",
        on_delete=models.CASCADE,
    )

    original_to = models.ForeignKey(
        "db.InterfacePin",
        related_name="adapters_original_to",
        null=True,  # nullable because we pre-create these adapters, but we can't know which pin maps to which
        blank=True,  # blankable on because we cannot save the model otherwise (becuase we always call clean)
        on_delete=models.CASCADE,
    )
    adapted_to = models.ForeignKey(
        "db.InterfacePin",
        related_name="adapters_adapted_to",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )

    # validation
    # - all adapters on the same interface have to agree on what a pin means
    # - all incompatible pins must be adapted

    def clean(self):
        # An adapter cannot adapt interfaces of its parent - if this turns out to be a problem we'll need to
        # rethink a lot about how bus fragments work.
        if (self.adapted_from_id and not self.bus_fragment.from_filter_id) or (
            self.adapted_to_id and not self.bus_fragment.to_filter_id
        ):
            raise ValidationError(
                "Adapters cannot change interfaces on their parent - "
                "change the child interface or add a compatible interface instead."
            )

        # An adapter is only valid if exactly one of "adapted_from" and "adapted_to" is filled out.
        # This is because the expected the adapter to change exactly one side of the bus fragment
        # (for example analog.0 -> digital.0 in an analog->digital bus.)

        if (
            (not self.adapted_from and not self.adapted_to)
            or self.adapted_from
            and self.adapted_to
        ):
            raise ValidationError(
                {
                    "adapted_from": "Exactly one of adapted_from and adapted_to should be filled out! "
                    "(One side of the bus fragment should be adapted to fit the other.)"
                }
            )

        effective_from_pin = self.adapted_from or self.original_from
        effective_to_pin = self.adapted_to or self.original_to
        adapted_field = "adapted_from" if self.adapted_from else "adapted_to"

        if not effective_from_pin.compatible_pins.filter(
            id=effective_to_pin.id
        ).exists():
            raise ValidationError(
                {
                    adapted_field: f"{effective_from_pin} is incompatible with {effective_to_pin}!"
                }
            )
