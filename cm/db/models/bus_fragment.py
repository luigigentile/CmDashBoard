from copy import copy

from django.core.exceptions import ValidationError
from django.db import models

from cm.db.fields import SmallTextField
from cm.db.models.base_model import BaseModel
from cm.db.models.interface_type import InterfaceType


class BusFragment(BaseModel):
    """A bus between two filters in a sub-circuit."""

    class Meta:
        verbose_name_plural = "Bus Fragments"
        unique_together = (
            ("name", "subcircuit"),
            ("from_filter", "to_filter", "from_interface", "to_interface"),
        )

    from_filter = models.ForeignKey(
        "db.BlockFilter",
        blank=True,
        null=True,
        verbose_name="from",
        on_delete=models.CASCADE,
        related_name="bus_fragments_from",
    )
    to_filter = models.ForeignKey(
        "db.BlockFilter",
        blank=True,
        null=True,
        verbose_name="to",
        on_delete=models.CASCADE,
        related_name="bus_fragments_to",
    )

    from_interface_type = models.ForeignKey(
        "db.InterfaceType",
        null=True,
        blank=True,
        related_name="bus_fragments_from",
        on_delete=models.PROTECT,
    )
    to_interface_type = models.ForeignKey(
        "db.InterfaceType",
        null=True,
        blank=True,
        related_name="bus_fragments_to",
        on_delete=models.PROTECT,
    )

    # from_interface and to_interface are used when a specific interface should be addressed.
    # Either one or both of these can be none, in which case any matching interface of the associated
    # interface type is used.
    from_interface = models.ForeignKey(
        "db.Interface",
        blank=True,
        null=True,
        related_name="bus_fragments_from",
        on_delete=models.CASCADE,
    )
    to_interface = models.ForeignKey(
        "db.Interface",
        blank=True,
        null=True,
        related_name="bus_fragments_to",
        on_delete=models.CASCADE,
    )

    # The name of this bus fragment, local to its sub-circuit. This gets translated into a global reference later.
    name = SmallTextField()

    # The fragment's sub-circuit is implicit via its filters, but it's denormalized here for easier access.
    subcircuit = models.ForeignKey(
        "db.SubCircuit", related_name="bus_fragments", on_delete=models.CASCADE
    )

    def get_function(self):
        from_function = (
            self.from_interface.get_function() if self.from_interface_id else None
        )
        to_function = self.to_interface.get_function() if self.to_interface_id else None
        interface_type_function = (
            self.interface_type.function if self.interface_type_id else None
        )

        if from_function and to_function and from_function != to_function:
            raise RuntimeError(
                f"Bus Fragment {self} has two different functions ({from_function} on from_interface "
                f"and {to_function} on to_interface. This behaviour is undefined!"
            )

        return from_function or to_function or interface_type_function

    def __str__(self):
        return f"{self.name} {self.from_filter}-{self.to_filter} ({self.from_interface}-{self.to_interface})"

    def clean(self):
        if not self.to_filter_id and not self.from_filter_id:
            raise ValidationError("At least one from or to filter must be set.")

        if not self.from_interface_type_id and not self.from_interface_id:
            raise ValidationError(
                "At least one of from_interface_type or from_interface must be set."
            )

        if not self.to_interface_type_id and not self.to_interface_id:
            raise ValidationError(
                "At least one of to_interface_type or to_interface must be set."
            )

        if self.subcircuit_id:
            # Check from_filter belongs to the sub-circuit
            if (
                self.from_filter_id
                and self.from_filter.subcircuit_id != self.subcircuit_id
            ):
                raise ValidationError(
                    {"from_filter": "From filter is not a child of the sub-circuit."}
                )
            # Check to_filter belongs to the sub-circuit
            if self.to_filter_id and self.to_filter.subcircuit_id != self.subcircuit_id:
                raise ValidationError(
                    {"to_filter": "To filter is not a child of the sub-circuit."}
                )

        if self.from_interface_type_id:
            # Check from_interface_type has no children
            if self.from_interface_type.children.exists():
                raise ValidationError(
                    {"from_interface_type": "From interface type must not be a parent."}
                )
            if self.from_filter_id:
                # Check from_interface_type is on from_filter's connectivity's interfaces (or a child of them)
                if not self.from_interface_type.is_child(
                    InterfaceType.objects.filter(
                        interfaces__connectivity=self.from_filter.connectivity
                    ),
                    include_self=True,
                ):
                    raise ValidationError(
                        {
                            "from_interface_type": "From interface type must be on from_filter's connectivity."
                        }
                    )
            elif self.subcircuit_id:
                # Or, check from_interface_type is on sub-circuit's connectivity's interfaces (or a child of them)
                if not self.from_interface_type.is_child(
                    InterfaceType.objects.filter(
                        interfaces__connectivity=self.subcircuit.connectivity
                    ),
                    include_self=True,
                ):
                    raise ValidationError(
                        {
                            "from_interface_type": "From interface type must be on sub-circuit's connectivity."
                        }
                    )

        if self.to_interface_type_id:
            # Check to_interface_type has no children
            if self.to_interface_type.children.exists():
                raise ValidationError(
                    {"to_interface_type": "To interface type must not be a parent."}
                )
            if self.to_filter_id:
                # Check to_interface_type is on to_filter's connectivity's interfaces (or a child of them)
                if not self.to_interface_type.is_child(
                    InterfaceType.objects.filter(
                        interfaces__connectivity=self.to_filter.connectivity
                    ),
                    include_self=True,
                ):
                    raise ValidationError(
                        {
                            "to_interface_type": "To interface type must be on to_filter's connectivity."
                        }
                    )
            elif self.subcircuit_id:
                # Or, check to_interface_type is on sub-circuit's connectivity's interfaces (or a child of them)
                if not self.to_interface_type.is_child(
                    InterfaceType.objects.filter(
                        interfaces__connectivity=self.subcircuit.connectivity
                    ),
                    include_self=True,
                ):
                    raise ValidationError(
                        {
                            "to_interface_type": "To interface type must be on sub-circuit's connectivity."
                        }
                    )

        if self.from_interface_id:
            if self.from_filter_id:
                # Check from_interface is on the from_filter's connectivity
                if not self.from_filter.connectivity.interfaces.filter(
                    id=self.from_interface_id
                ).exists():
                    raise ValidationError(
                        {
                            "from_interface": "From interface must be on from_filter connectivity."
                        }
                    )
            elif self.subcircuit_id:
                # Or, check from_interface is on the sub-circuit's connectivity
                if not self.subcircuit.connectivity.interfaces.filter(
                    id=self.from_interface_id
                ).exists():
                    raise ValidationError(
                        {
                            "from_interface": "From interface must be on sub-circuit connectivity."
                        }
                    )
            # Check from_interface's interface type is an ancestor of from_interface_type
            if (
                self.from_interface_type_id
                and not self.from_interface_type.get_ancestors(include_self=True)
                .filter(id=self.from_interface.interface_type_id)
                .exists()
            ):
                raise ValidationError(
                    {
                        "from_interface": (
                            "From interface's interface type must be the same "
                            "or an ancestor of from_interface_type."
                        )
                    }
                )

        if self.to_interface_id:
            if self.to_filter_id:
                # Check to_interface is on the to_filter's connectivity
                if not self.to_filter.connectivity.interfaces.filter(
                    id=self.to_interface_id
                ).exists():
                    raise ValidationError(
                        {
                            "to_interface": "To interface must be on from_filter connectivity."
                        }
                    )
            elif self.subcircuit_id:
                # Or, check to_interface is on the sub-circuit's connectivity
                if not self.subcircuit.connectivity.interfaces.filter(
                    id=self.to_interface_id
                ).exists():
                    raise ValidationError(
                        {
                            "to_interface": "To interface must be on sub-circuit connectivity."
                        }
                    )
            # Check to_interface's interface type is an ancestor of to_interface_type
            if (
                self.to_interface_type_id
                and not self.to_interface_type.get_ancestors(include_self=True)
                .filter(id=self.to_interface.interface_type_id)
                .exists()
            ):
                raise ValidationError(
                    {
                        "to_interface": (
                            "To interface's interface type must be the same "
                            "or an ancestor of to_interface_type."
                        )
                    }
                )

        # Check from_interface and to_interface are not the same interface
        if (
            self.from_interface_id
            and self.to_interface_id
            and (
                (self.from_interface_id == self.to_interface_id)
                and (self.from_filter_id == self.to_filter_id)
            )
        ):
            raise ValidationError(
                "from_interface and to_interface cannot be the same interface"
            )

    def duplicate(self, subcircuit_id):
        """Create a duplicate instance of this bus fragment, attached to the subcircuit with id <subcircuit_id>."""
        duplicate_instance = copy(self)
        duplicate_instance.pk = None
        duplicate_instance.subcircuit_id = subcircuit_id

        # Now duplicate the bus fragment's filters.
        duplicate_instance.from_filter = self.from_filter.duplicate(
            subcircuit_id=subcircuit_id
        )
        if self.from_filter_id != self.to_filter_id:
            duplicate_instance.to_filter = self.to_filter.duplicate(
                subcircuit_id=subcircuit_id
            )
        else:
            duplicate_instance.to_filter = duplicate_instance.from_filter

        duplicate_instance.save()

        return duplicate_instance
