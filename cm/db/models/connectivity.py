from copy import copy

from django.db import models

from cm.db.fields import SmallTextField

from .base_model import BaseModel
from .schematic_symbol import SchematicSymbol


class Connectivity(BaseModel):
    class Meta:
        verbose_name = "Connectivity"
        verbose_name_plural = "Connectivities"

    name = SmallTextField(unique=True)

    schematic_symbol = models.ManyToManyField(SchematicSymbol, blank=True)

    simplified_connectivity = models.TextField(
        "Simplified connectivity notes",
        help_text=(
            "If this connectivity differs in function from its datasheet or is otherwise simplified to overcome "
            "software limitations, please add some notes about this here."
        ),
        blank=True,
        default="",
    )

    use_for_ancillaries = models.BooleanField(
        default=False,
        help_text="Determines whether this connectivity can be used as an ancillary component.",
    )

    def __str__(self):
        return self.name

    def assign(self, pin, interface, interface_pin):
        """Assign a pin to an interface, acting as a particular interface pin.

        Note that this is an expensive operation because we resave all existing assignments first.
        We do that so all cached pin ids are up-to-date and we can avoid having to do complex work
        to find out if the pin is already assigned.
        """
        from .pin_assignment import PinAssignment  # avoid circular import

        existing_assignments = PinAssignment.objects.filter(
            interface=interface, interface_pin=interface_pin,
        )
        for assignment in existing_assignments:
            # Save all existing assignments to make sure the pin id cache is up-to-date
            assignment.save()

        # If the pin is already assigned, do nothing
        if existing_assignments.filter(pins=pin).exists():
            return existing_assignments.filter(pins=pin).first()

        # Before creating a new assignment we'll check if an independent assignment already exists,
        # which we can just add this pin to.
        existing_assignment = PinAssignment.objects.filter(
            interface=interface,
            interface_pin=interface_pin,
            pin_identifiers_type=PinAssignment.PinIdentifierType.independent,
        ).first()

        if existing_assignment:
            existing_identifiers = existing_assignment.pin_identifiers.split(",")
            existing_assignment.pin_identifiers = ",".join(
                list(set(existing_identifiers) | set([pin.number]))
            )
            existing_assignment.save()
            return existing_assignment
        else:
            # Nothing exists yet, so create a new assignment object
            return PinAssignment.objects.create(
                interface=interface,
                interface_pin=interface_pin,
                pin_identifiers=pin.number,
            )

    def duplicate(self):
        """Save a copy of this connectivity object.

        If the unsaved instance hasn't been changed from the db state,
        some fields will be updated to reflect the copy, otherwise the changed data
        is just saved with a new id.

        Specific reverse-related objects, like pins and interfaces, will also be duplicated.
        """
        from .pin_assignment import PinAssignment  # avoid circular import

        duplicate_instance = copy(self)
        existing = Connectivity.objects.get(pk=self.pk)

        # First copy the connectivity itself
        duplicate_instance.pk = None
        if duplicate_instance.name == existing.name:
            duplicate_instance.name += " (Copy)"
        duplicate_instance.save()

        # Duplicate interfaces and remember the mapping from old to new
        # This needs to happen in two stages, copying parent interfaces first, then copying children
        # This is required so that we can pass the copied parent id to the new child
        interface_copy_map = {}  # {old_id: new_id}
        for parent_interface in existing.interfaces.filter(parent_id__isnull=True):
            duplicated_interface = parent_interface.duplicate(
                connectivity_id=duplicate_instance.pk
            )
            interface_copy_map[parent_interface.id] = duplicated_interface.id

        for child_interface in existing.interfaces.filter(parent_id__isnull=False):
            duplicated_interface = child_interface.duplicate(
                connectivity_id=duplicate_instance.pk,
                parent_id=interface_copy_map[child_interface.parent_id],
            )
            interface_copy_map[child_interface.id] = duplicated_interface.id

        # Duplicate pins for the new connectivity object
        for pin in existing.pins.all():
            pin.duplicate(
                connectivity_id=duplicate_instance.pk,
                voltage_reference_id=interface_copy_map.get(pin.voltage_reference_id),
            )

        # Copy the assignments - we don't need to do anything special here, but we do need to make sure that the
        # parent assignments are created before the child assignments, because validation on the child assignments
        # will try and access parent assignments.
        # We can accomplish this simply by sorting
        pin_assignments = PinAssignment.objects.filter(
            interface__connectivity=existing,
        ).order_by(
            "-parent_interface_pin"
        )  # Child interfaces last
        for assignment in pin_assignments:
            assignment.duplicate(
                interface_id=interface_copy_map[assignment.interface_id]
            )

        return duplicate_instance

    def last_change(self):
        """Return the timestamp of the last change of the connectivity or its related objects."""
        from .interface_pin import InterfacePin
        from .interface_type import InterfaceType
        from .pin_assignment import PinAssignment

        def _last_change(qs):
            return qs.order_by("-updated").values_list("updated", flat=True).first()

        last_changes = [
            self.updated,
            _last_change(self.pins.all()),
            _last_change(self.interfaces.all()),
            _last_change(PinAssignment.objects.filter(interface__connectivity=self)),
            _last_change(InterfaceType.objects.all()),
            _last_change(InterfacePin.objects.all()),
        ]

        return max([change for change in last_changes if change is not None])

    @property
    def function(self):
        """Describes the function of this connectivity in the circuit.

        For now this is just the category slug."""

        return self.block_set.values_list("categories__slug", flat=True).first()
