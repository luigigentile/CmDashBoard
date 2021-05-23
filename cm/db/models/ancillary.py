from copy import copy
from typing import Dict, Optional, Union, cast
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import models, transaction

from cm.db.attribute_field.transform import decode_form_value
from cm.db.constants import (
    ANCILLARY_TYPE_MAP,
    AncillaryConnectionRole,
    AncillaryOperator,
    AncillaryTarget,
    ConnectionType,
    DBAncillaryAppliesTo,
    DBAncillaryType,
)
from cm.db.fields import SmallTextField
from cm.db.models import (
    AttributeDefinition,
    Block,
    Category,
    Connectivity,
    Interface,
    InterfaceFamily,
    InterfacePin,
    InterfaceType,
    Pin,
    PinAssignment,
    SubCircuit,
)

from .base_model import BaseModel

TargetType = Union[Interface, InterfaceType, InterfaceFamily, Pin]


class Ancillary(BaseModel):
    # Ancillary components can be added to a number of different objects.
    # Only one of these can be set at once!
    interface = models.ForeignKey(
        Interface,
        related_name="ancillaries",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    interface_type = models.ForeignKey(
        InterfaceType,
        related_name="ancillaries",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    interface_family = models.ForeignKey(
        InterfaceFamily,
        related_name="ancillaries",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )

    # Sub-circuit ancillaries apply to a specific interface only within the specified sub-circuit
    subcircuit = models.ForeignKey(
        SubCircuit,
        related_name="ancillaries",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )

    ancillary_type = SmallTextField(choices=DBAncillaryType.choices)
    applies_to = SmallTextField(
        choices=DBAncillaryAppliesTo.choices,
        help_text=(
            "Pick what this ancillary applies to - to the pins of the bus, or the bus itself. "
            "Note that bus ancillaries can only be configured on interface families."
        ),
    )

    # This is the connectivity used for the ancillary component.
    connectivity = models.ForeignKey(
        Connectivity,
        related_name="ancillaries",
        on_delete=models.CASCADE,
        limit_choices_to={"use_for_ancillaries": True},
    )

    maximum_latency = models.FloatField(
        help_text="Maximum signal latency from pin in picoseconds. Only applies to interface ancillary!",
        default=0,
    )

    def __str__(self):
        return DBAncillaryType.labels[self.ancillary_type] + "-" + str(self.id)
   

    def get_interface_type(self):
        return self.interface_type
    
    def _target_objects(self) -> Dict[str, UUID]:
        """Returns a dict describing which objects this instance is related to.

        We need this because a ancillary can be defined on various different types,
        this keeps the logical related to that in a single place. """

        possible_target_objects = {
            AncillaryTarget.interface: self.interface_id,
            AncillaryTarget.interface_type: self.interface_type_id,
            AncillaryTarget.interface_family: self.interface_family_id,
        }
        return {k: v for k, v in possible_target_objects.items() if v}

    def clean(self):
        target_objects = self._target_objects()

        # Non-custom connectivities must have exactly two pins
        if not self.connectivity_id or len(self.connectivity.pins.all()) != 2:
            raise ValidationError(
                {
                    "connectivity": "Standard ancillaries require a connectivity with exactly two pins!"
                }
            )

        # Ancillary must be related to exactly one object, except for pin ancillaries.
        if len(target_objects) != 1 and self.applies_to != DBAncillaryAppliesTo.pins:
            error_msg = (
                f"{self.applies_to} ancillary must target exactly one of interface/type/family, "
                f"got {len(target_objects)}."
            )
            if len(target_objects):
                error_msg += f' ({", ".join(target_objects.keys())})'
            raise ValidationError(error_msg)
        if len(target_objects) and self.applies_to == DBAncillaryAppliesTo.pins:
            raise ValidationError(
                "Pin ancillaries should not specify a target interface/type/family!"
            )

        # We're now guaranteed to have exactly one target, except for pin ancillaries
        if self.applies_to == DBAncillaryAppliesTo.pins:
            target_type = target_id = None
        else:
            target_type, target_id = list(target_objects.items())[0]

        # Sub-circuit ancillaries cannot be defined on buses
        if self.subcircuit_id and self.applies_to == DBAncillaryAppliesTo.bus:
            raise ValidationError(
                "Sub-circuit ancillaries must be defined on interfaces"
            )

        # Latency constraints are only allowed on interface ancillaries
        if (
            self.applies_to != DBAncillaryAppliesTo.interface
            and self.maximum_latency > 0
        ):
            raise ValidationError(
                {
                    "maximum_latency": "Maximum latency is only applicable for interface ancillaries!"
                }
            )

        # Check that target objects and "applies_to" match
        if (
            self.applies_to == DBAncillaryAppliesTo.bus
            and target_type != AncillaryTarget.interface_family
        ):
            raise ValidationError(
                {
                    "applies_to": "Bus ancillaries can only be configured for interface families."
                }
            )
        elif self.applies_to == DBAncillaryAppliesTo.interface and target_type not in (
            AncillaryTarget.interface_type,
            AncillaryTarget.interface,
        ):
            raise ValidationError(
                {
                    "applies_to": "Interface ancillaries can only be configured for interfaces or interface types."
                }
            )

        # Don't allow ancillaries on child interface types, we always want them at the top level
        if self.interface_type and self.interface_type.parents.exists():
            raise ValidationError(
                f"Ancillary has to be added on the parent interface type(s) "
                f'({", ".join(p.name for p in self.interface_type.parents.all())})'
            )

        # Only allow parallel ancillaries on buses, we can't deal with any other types yet
        if (
            self.applies_to == DBAncillaryAppliesTo.bus
            and self.connection_type != ConnectionType.parallel
        ):
            raise ValidationError(
                {"applies_to": "Only parallel ancillaries are supported on buses."}
            )

    def duplicate(self, interface_id=None):
        """Create a duplicate instance of this ancillary.

        Pass interface_id to reassign the copy to a new interface.
        """
        duplicate_instance = copy(self)
        duplicate_instance.pk = None

        if interface_id:
            duplicate_instance.interface_id = interface_id
        duplicate_instance.save()

    def get_category(self) -> Category:
        """Get the part category that applies to this ancillary."""
        return cast(
            Category,
            Category.objects.filter(block__connectivity=self.connectivity).first(),
        )

    def get_main_attributes(self):
        """Returns the two main attributes that are generally used to specify a ancillary.

        This is purely a convenience to make it easier to edit ancillaries without having to make a lot of clicks
        in the admin. """
        category = self.get_category()
        parent_categories = category.get_ancestors(include_self=True)

        capacitor_slug = ANCILLARY_TYPE_MAP[DBAncillaryType.decoupling_capacitor]
        resistor_slug = ANCILLARY_TYPE_MAP[DBAncillaryType.pull_up_resistor]
        ferrite_bead_slug = ANCILLARY_TYPE_MAP[DBAncillaryType.ferrite_bead]

        if category.slug == capacitor_slug:
            # For capacitors, the main attributes are capacitance and tolerance
            return [
                AttributeDefinition.objects.get(
                    category__in=parent_categories, name="capacitance"
                ),
                AttributeDefinition.objects.get(
                    category__in=parent_categories, name="tolerance_+"
                ),
            ]
        if category.slug == resistor_slug:
            # For resistors, the main attributes are resistance and tolerance
            return [
                AttributeDefinition.objects.get(
                    category__in=parent_categories, name="resistance"
                ),
                AttributeDefinition.objects.get(
                    category__in=parent_categories, name="tolerance_+"
                ),
            ]
        if category.slug == ferrite_bead_slug:
            # For ferrite beads, the main attributes are impedance at a given frequency and dc resistance
            return [
                AttributeDefinition.objects.get(
                    category__in=parent_categories, name="impedance_@_frequency"
                ),
                AttributeDefinition.objects.get(
                    category__in=parent_categories, name="dc_resistance"
                ),
            ]
        raise RuntimeError(f"No main attributes configured for category {category}")

    def get_interface_type_ids(self):
        """Get the IDs of interface types that apply to this ancillary."""
        if self.interface_type_id:
            return [self.interface_type_id]
        elif self.interface_id:
            return [self.interface.interface_type_id]
        elif self.interface_family_id:
            return self.interface_family.interface_types.filter(
                can_be_required=True
            ).values_list("id", flat=True)
        else:
            return []

    @property
    def connection_type(self) -> Optional[str]:
        """A rough classification of ancillaries into parallel and series ancillaries.

        This is needed to figure out how to connect a part in the wider circuit. In the future, there
        will likely be other connection types as well, like ancillaries that bridge two pins on a component."""
        if self.ancillary_type in (
            DBAncillaryType.decoupling_capacitor,
            DBAncillaryType.pull_up_resistor,
            DBAncillaryType.pull_up_capacitor,
            DBAncillaryType.pull_down_resistor,
            DBAncillaryType.pull_down_capacitor,
        ):
            return ConnectionType.parallel
        elif self.ancillary_type in (
            DBAncillaryType.series_resistor,
            DBAncillaryType.series_capacitor,
            DBAncillaryType.ferrite_bead,
        ):
            return ConnectionType.series
        elif self.ancillary_type == DBAncillaryType.custom:
            return None
        raise RuntimeError(f"Unknown ancillary type '{self.ancillary_type}'")

    @transaction.atomic  # type: ignore
    def create_standard_connections(
        self,
        interface_pin: Optional[InterfacePin],
        pin: Optional[Pin],
        pin_assignment: PinAssignment = None,
    ) -> None:
        """Creat the connections for a standard ancillary (pull-up/down, series resistor, ...).

        Note that while pin ancillaries support connections with multiple pins, the standard ancillaries that are
        created using this method only support a single pin!
        """
        # The first connection is easy, it always connects the first ancillary pin to the connectivity
        connectivity_pins = self.connectivity.pins.all()
        AncillaryConnection.objects.create(
            ancillary=self,
            interface_pin=interface_pin,
            pin=pin,
            ancillary_pin=connectivity_pins[0],
            role=AncillaryConnectionRole.input,
            pin_assignment=pin_assignment,
        )

        # Series ancillaries need an output pin which acts to mask the input pin for the rest of the circuit
        if self.connection_type == ConnectionType.series:
            AncillaryConnection.objects.create(
                ancillary=self,
                interface_pin=interface_pin,
                pin=pin,
                ancillary_pin=connectivity_pins[1],
                role=AncillaryConnectionRole.output,
                pin_assignment=None,  # pin assignment is only important for the input pin
            )

        # Parallel connections get a second connection object to their power/gnd reference
        if self.connection_type == ConnectionType.parallel:
            if self.ancillary_type in [
                DBAncillaryType.pull_up_capacitor,
                DBAncillaryType.pull_up_resistor,
            ]:
                # Connect to the reference voltage
                role = AncillaryConnectionRole.v_ref
            elif self.ancillary_type in [
                DBAncillaryType.pull_down_capacitor,
                DBAncillaryType.pull_down_resistor,
                DBAncillaryType.decoupling_capacitor,
            ]:
                role = AncillaryConnectionRole.gnd_ref
            else:
                raise RuntimeError(
                    f"create_standard_ancillary got unsupported ancillary type {self.ancillary_type}!"
                )

            AncillaryConnection.objects.create(
                ancillary=self,
                interface_pin=interface_pin,
                pin=pin,
                ancillary_pin=connectivity_pins[1],
                role=role,
                pin_assignment=None,  # pin assignment is only important for the input pin
            )

    @classmethod
    def create_standard_ancillary(
        cls,
        ancillary_type: str,
        applies_to: str,
        ancillary_connectivity: Connectivity,
        target: TargetType,
        interface_pin: Optional[InterfacePin],
        pin: Optional[Pin],
        maximum_latency: int = 0,
        block: Block = None,
        pin_assignment: PinAssignment = None,
    ) -> "Ancillary":
        # A few sanity checks
        if ancillary_type == DBAncillaryType.custom:
            raise RuntimeError(
                "Cannot construct custom ancillaries with create_standard_ancillary!"
            )
        if interface_pin and pin:
            raise RuntimeError(
                "Exactly one of pin/interface_pin should be passed to create_standard_ancillary!"
            )
        if interface_pin and applies_to == DBAncillaryAppliesTo.pins:
            raise RuntimeError("Got interface_pin for pin ancillary, expected pin!")
        if pin and applies_to != DBAncillaryAppliesTo.pins:
            raise RuntimeError("Got pin for non-pin ancillary, expected interface pin!")

        # Arguments for the constructor that don't need any processing
        ancillary_args = {
            "ancillary_type": ancillary_type,
            "applies_to": applies_to,
            "connectivity": ancillary_connectivity,
            "maximum_latency": maximum_latency,
        }

        # Process the valid choices for the targets of this ancillary
        target_type: Optional[str]
        if isinstance(target, Interface):
            target_type = AncillaryTarget.interface
        elif isinstance(target, InterfaceType):
            target_type = AncillaryTarget.interface_type
        elif isinstance(target, InterfaceFamily):
            target_type = AncillaryTarget.interface_family
        elif isinstance(target, Pin):
            target_type = None
        else:
            raise RuntimeError(f"Unsupported ancillary target {target}!")
        if target_type:
            ancillary_args[target_type] = target

        # Process the valid choices for the block (currently subcircuits) that the ancillary can be filtered on.
        if block:
            if isinstance(block, SubCircuit):
                ancillary_args["subcircuit"] = block
            else:
                raise RuntimeError(
                    f"Unsupported block {block} for filtering ancillary!"
                )

        # Construct the ancillary object
        ancillary = cls(**ancillary_args)

        # Now create the connection objects
        with transaction.atomic():
            ancillary.save()
            ancillary.create_standard_connections(
                interface_pin=interface_pin, pin=pin, pin_assignment=pin_assignment,
            )

        return ancillary


class AncillaryConnection(BaseModel):
    ancillary = models.ForeignKey(
        Ancillary, related_name="connections", on_delete=models.CASCADE
    )

    # ********** Ancillary target - can be a pin or an interface pin **********
    # The interface pin the ancillary is connected to
    # Note: interface ancillaries apply only to a specific interface pin, but bus ancillaries are a bit more complex.
    # They actually apply to a whole logical net, but we still just reference one interface_pin.
    # This pin is the requesting pin of the logical net, which uniquely identifies the net.
    interface_pin = models.ForeignKey(
        InterfacePin,
        related_name="ancillary_connections",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    pin = models.ForeignKey(
        Pin,
        related_name="ancillary_connections",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )

    # The pin on the ancillary's connectivity this connection explains
    ancillary_pin = models.ForeignKey(
        Pin, related_name="pin_ancillary_connections", on_delete=models.CASCADE
    )

    # This field describes the special case of an ancillary pin connecting to power/gnd.
    # Which power/gnd it connects to probably needs to be specified more in the future, for now this is only
    # used on pull-up/pull-down parts where the choice is very easy.
    role = SmallTextField(
        choices=AncillaryConnectionRole.choices,
        help_text=(
            "The role this pin plans on the ancillary. "
            "Inputs connect to the target, outputs to the rest of the circuit. "
            "Other options define special actions like connecting to a reference voltage."
        ),
    )

    # For interface ancillaries only, this pin assignment describes the pin(s) this ancillary gets connected to.
    # If none is defined, an arbitrary pin assignment with the right interface pin is picked.
    pin_assignment = models.ForeignKey(
        PinAssignment,
        related_name="ancillary_connections",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )

    def __str__(self):
        return (
            f"{self.ancillary_pin} - ({self.role}) for {self.interface_pin or self.pin}"
        )

    def clean(self):
        if self.ancillary.applies_to == DBAncillaryAppliesTo.bus:
            if self.pin_assignment_id:
                raise ValidationError(
                    {
                        "pin_assignment": "Bus ancillaries cannot have connectivity pins assigned!"
                    }
                )

        if (
            not self.interface_pin_id
            and self.ancillary.applies_to != DBAncillaryAppliesTo.pins
        ):
            raise ValidationError(
                {
                    "interface_pin": "Only pin ancillaries should not specify an interface pin!"
                }
            )

        if not self.pin_id and self.ancillary.applies_to == DBAncillaryAppliesTo.pins:
            raise ValidationError({"pin": "Pin is required for pin ancillaries!"})


class AncillaryAttribute(BaseModel):
    ancillary = models.ForeignKey(
        Ancillary, related_name="attributes", on_delete=models.CASCADE
    )
    attribute_definition = models.ForeignKey(
        "db.AttributeDefinition", on_delete=models.PROTECT
    )
    operator = SmallTextField(choices=AncillaryOperator.choices)
    value = SmallTextField()

    def __str__(self):
        return f"{self.attribute_definition.name} {self.operator} {self.value}"

    def duplicate(self, ancillary_id=None):
        """Create a duplicate instance of this attribute."""
        duplicate_instance = copy(self)
        duplicate_instance.pk = None

        if ancillary_id:
            duplicate_instance.ancillary_id = ancillary_id
        duplicate_instance.save()

    def clean(self):
        # Make sure the entered value matches its attribute definition
        # We store the value as entered, but we need to make sure it validates for the given unit/datatype.
        try:
            decode_form_value(
                name=str(self.attribute_definition),
                value=self.value,
                attribute_definition=self.attribute_definition,
            )
        except ValueError as e:
            raise ValidationError({"value": f"{e}"})

        # Make sure that the attribute definition's category matches the parent ancillary's category
        try:
            category = self.ancillary.get_category()
        except Category.DoesNotExist:
            if self.attribute_definition is not AttributeDefinition.objects.none():
                raise ValidationError(
                    "The ancillary attribute category must match the ancillary type. "
                )
        else:
            if self.attribute_definition.category not in category.get_ancestors(
                include_self=True
            ):
                raise ValidationError(
                    "The ancillary attribute category must match the ancillary type. "
                )
