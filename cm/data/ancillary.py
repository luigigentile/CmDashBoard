from dataclasses import dataclass
from functools import reduce
from operator import add
from typing import TYPE_CHECKING, Dict, FrozenSet, List, Optional, Set, Tuple, cast
from uuid import UUID

from django.contrib.postgres.fields.jsonb import KeyTextTransform
from django.db.models import FloatField, Value
from django.db.models.functions import Cast

from cm.data.bus import Bus
from cm.data.component_interface import ComponentInterface
from cm.data.component_pin import ComponentPin
from cm.data.pin_assignment import PinAssignment
from cm.db import models, query
from cm.db.constants import AncillaryAppliesTo, AncillaryConnectionRole, AncillaryType
from cm.exceptions import LibraryError

if TYPE_CHECKING:
    from cm.data.component import Component


class InvalidAncillaryError(Exception):
    pass


class ReferenceError(Exception):
    """Raised if an ancillary cannot be connected because of a problem with its voltage/power reference."""

    pass


@dataclass
class AppliedConnection:
    """Simple data structure containing information about how an ancillary connection is applied.

    It contains
        - A set of tuples showing which pins to connect together in the circuit
        - A mapping of input pins to output pins, showing which pins get masked by ancillaries.

    The mapping takes the form of {input_pin: output_pin}.
    If an ancillary has a series connection, the input pin becomes hidden to the rest of the circuit,
    having been replaced by the output pin.

    Example:
        A component has a digital pin "A"
        "A" has a series resistor pin ancillary
        Pin 1 of the resistor is the input and connects to pin A
        Pin 2 of the resistor is the output.

        As far as the rest of the circuit is concerned, anything that would connect to A
        now connects to resistor pin 2 instead.
    """

    pin_connections: Set[Tuple[ComponentPin, ComponentPin]]
    pin_mask: Dict[ComponentPin, ComponentPin]


def _ancillary_ordering(ancillary: "Ancillary") -> int:
    """Sorting key function for ancillaries.

    Gives ancillaries a rank depending on their ancillary type. """

    order_map = {
        AncillaryType.custom: 0,
        AncillaryType.series_capacitor: 1,
        AncillaryType.series_resistor: 2,
        AncillaryType.ferrite_bead: 3,
        AncillaryType.decoupling_capacitor: 4,
        AncillaryType.pull_up_resistor: 5,
        AncillaryType.pull_up_capacitor: 6,
        AncillaryType.pull_down_resistor: 7,
        AncillaryType.pull_down_capacitor: 8,
        AncillaryType.connector: 9,
    }
    if ancillary.ancillary_type not in order_map:
        raise KeyError(f"Ancillary type {ancillary.ancillary_type} has no ordering!")
    return order_map[ancillary.ancillary_type]


@dataclass(frozen=True, eq=True)
class AncillaryConnection:
    """Defines how an ancillary connects to other components in a circuit."""

    pin_assignment: Optional[
        PinAssignment
    ]  # Ancillary is connected to the pins chosen for this assignment

    ancillary_pin_id: UUID

    # pin_id should be None for all ancillaries except pin ancillaries
    pin_id: Optional[UUID]
    # interface_pin_id should only be None for pin ancillaries
    interface_pin_id: Optional[UUID]

    # The role this pin plans on the ancillary. Inputs connect to the target, outputs to the rest of the circuit.
    # Other options define special actions like connecting to a reference voltage.
    role: str

    def __str__(self) -> str:
        return f"{self.role} for {self.interface_pin_id or self.pin_id}"

    @classmethod
    def from_db(
        cls,
        db_connection: models.AncillaryConnection,
        parent_component: Optional["Component"],
        interface: Optional[ComponentInterface],
        applies_to: AncillaryAppliesTo,
    ) -> "AncillaryConnection":

        pin_assignment: Optional[PinAssignment] = None

        if applies_to != AncillaryAppliesTo.bus and not parent_component:
            # The only terminations that don't have parents are bus terminations.
            raise RuntimeError("Non-bus ancillaries must have a parent component!")

        if applies_to == AncillaryAppliesTo.interface:
            if not interface:
                raise RuntimeError("Interface ancillaries must have an interface!")

            pin_assignment = None
            if db_connection.pin_assignment_id:
                # A pin assignment was specified by the user
                pin_assignment = interface.interface.get_pin_assignment(
                    db_connection.pin_assignment_id
                )

        return cls(
            interface_pin_id=db_connection.interface_pin_id,
            pin_id=db_connection.pin_id,
            pin_assignment=pin_assignment,
            ancillary_pin_id=db_connection.ancillary_pin_id,
            role=db_connection.role,
        )

    def voltage_reference_pin(
        self, input_pins: Set[ComponentPin]
    ) -> Optional[ComponentPin]:
        voltage_references = set(
            pin.component.get_pin(pin.pin.voltage_reference_pin_id)
            for pin in input_pins
            if pin.pin.voltage_reference_pin_id
        )
        if not voltage_references:
            return None

        # For now, we simply assume that all voltage references that show up on a bus are equivalent.
        # We arbitrarily pick the one with the lowest pin number.
        return sorted(
            voltage_references, key=lambda pin: (pin.pin.number, pin.pin.name)
        )[0]

    def gnd_reference_pin(
        self, input_pins: Set[ComponentPin]
    ) -> Optional[ComponentPin]:
        gnd_references = set(
            pin.component.get_pin(pin.pin.gnd_reference_pin_id)
            for pin in input_pins
            if pin.pin.gnd_reference_pin_id
        )
        if not gnd_references:
            return None

        # For now, we simply assume that all gnd references that show up on a bus are equivalent.
        # We arbitrarily pick the one with the lowest pin number.
        return sorted(gnd_references, key=lambda pin: (pin.pin.number, pin.pin.name))[0]

    def input_pins(self, ancillary: "Ancillary") -> Set[ComponentPin]:
        """Return the input pins of this ancillary from its parent component.

        Note this method only makes sense on non-bus ancillaries, because we need a parent."""
        if ancillary.applies_to == AncillaryAppliesTo.bus:
            raise RuntimeError("input_pins called on a bus ancillary!")
        assert ancillary.parent

        # Get the ancillary's target pins
        if ancillary.interface:
            # For interface ancillaries, get the pins straight from the interface
            return ancillary.interface.active_pins(
                interface_pin_id=self.interface_pin_id,
                pin_assignment=self.pin_assignment,
            )
        if self.pin_id:
            # Pin ancillaries are trivial, just get the pin from the parent
            return set([ancillary.parent.get_pin(self.pin_id)])

        raise RuntimeError(
            "Cannot calculate input pins, ancillary has no pin or interface!"
        )

    def apply(
        self, ancillary_component: "Component", input_pins: Set[ComponentPin] = None
    ) -> AppliedConnection:
        """Apply this connection in a circuit.

        Interface/pin ancillaries can figure out their own input pins, but bus ancillaries need to have
        their input pins passed in. This will raise an exception if input pins aren't supplied when they should be.

        The return value is an object describing both how the pins of this connection are connected to the rest of the
        circuit, as well as a mask that shows which input pins are being hidden by the ancillary.
        """
        ancillary = ancillary_component.ancillary
        assert ancillary

        if input_pins is None and ancillary.applies_to == AncillaryAppliesTo.bus:
            raise RuntimeError(
                "AncillaryConnection.apply requires explicitly passed-in input pins for bus ancillaries!"
            )
        input_pins = input_pins or self.input_pins(ancillary)

        ancillary_pin = ancillary_component.get_pin(self.ancillary_pin_id)
        voltage_reference = self.voltage_reference_pin(input_pins)
        gnd_reference = self.gnd_reference_pin(input_pins)

        if self.role == AncillaryConnectionRole.input:
            return AppliedConnection(
                pin_connections=set(
                    (input_pin, ancillary_pin) for input_pin in input_pins
                ),
                pin_mask={},  # Any pin masks will be defined by output connections later
            )
        elif self.role == AncillaryConnectionRole.output:
            return AppliedConnection(
                pin_connections=set(),  # Outputs don't need to connect to anything yet, just expose a pin
                pin_mask={
                    input_pin: ancillary_pin for input_pin in input_pins
                },  # All input pins (of this specific connections) get masked by the output pin
            )
        elif self.role == AncillaryConnectionRole.v_ref:
            # Note: there's currently no chance that voltage references get their ancillaries
            # before other components do, so this connection might wrongly point to power pins
            # that should be masked by ancillaries.
            if not voltage_reference:
                raise LibraryError(f"No voltage reference for {self}")
            return AppliedConnection(
                pin_connections=set([(ancillary_pin, voltage_reference)]),
                pin_mask={},  # no masking necessary for reference connections
            )
        elif self.role == AncillaryConnectionRole.gnd_ref:
            # Note: there's currently no chance that gnd references get their ancillaries
            # before other components do, so this connection might wrongly point to gnd pins
            # that should be masked by ancillaries.
            if not gnd_reference:
                raise LibraryError(f"No gnd reference for {self}")
            return AppliedConnection(
                pin_connections=set([(ancillary_pin, gnd_reference)]),
                pin_mask={},  # no masking necessary for reference connections
            )
        else:
            raise RuntimeError(f"Unknown Ancillary role {self.role}")


@dataclass(frozen=True, eq=True)
class Ancillary:
    """This class represents a concrete ancillary in a circuit.

    It's analogous to and points at cm.db.models.Ancillary."""

    id: Optional[UUID]  # id of the corresponding models.Ancillary object
    component_reference: str  # reference of the ancillary component
    ancillary_type: AncillaryType
    applies_to: AncillaryAppliesTo
    maximum_latency: float
    connection_type: Optional[str]
    connections: FrozenSet[AncillaryConnection]

    bus: Optional[Bus] = None  # Only for bus ancillaries
    board: Optional["Component"] = None  # Only for board ancillaries (connectors)

    interface: Optional[ComponentInterface] = None
    parent: Optional["Component"] = None  # the component requiring ancillary

    @property
    def ancillary_type_label(self) -> str:
        return str(AncillaryType.labels[self.ancillary_type])

    def __post_init__(self) -> None:
        if self.applies_to == AncillaryAppliesTo.bus and not self.bus:
            raise LibraryError("Bus ancillaries have to specify a bus!")
        if self.ancillary_type != AncillaryType.connector and not self.connections:
            raise LibraryError("Ancillary has no connections defined!")
        if self.applies_to != AncillaryAppliesTo.pins and not all(
            connection.interface_pin_id for connection in self.connections
        ):
            raise LibraryError(
                "All connections must specify an interface pin, except on pin ancillaries!"
            )

    def __str__(self) -> str:
        return f"{self.ancillary_type} {self.component_reference}"

    def family_label(self) -> str:
        if self.interface:
            return self.interface.interface_type.family.label
        if self.bus:
            return self.bus.interface_family().label
        return ""

    @classmethod
    def from_db(
        cls,
        db_ancillary: models.Ancillary,
        reference: str,
        bus: Bus = None,
        interface: ComponentInterface = None,
        parent: "Component" = None,
    ) -> "Ancillary":
        connections: FrozenSet[AncillaryConnection] = frozenset()
        connections = frozenset(
            AncillaryConnection.from_db(
                ancillary_connection,
                parent_component=parent,
                interface=interface,
                applies_to=db_ancillary.applies_to,
            )
            for ancillary_connection in db_ancillary.connections.all()
        )

        if bus and db_ancillary.applies_to == AncillaryAppliesTo.bus:
            return cls(
                id=db_ancillary.id,
                component_reference=reference,
                ancillary_type=db_ancillary.ancillary_type,
                applies_to=db_ancillary.applies_to,
                connection_type=db_ancillary.connection_type,
                connections=connections,
                bus=bus,
                parent=None,  # bus ancillaries don't have a parent!
                interface=None,  # bus ancillaries don't belong to a specific interface!
                maximum_latency=0,  # bus ancillaries never have timing constraints
            )
        elif (
            interface
            and parent
            and db_ancillary.applies_to == AncillaryAppliesTo.interface
        ):
            matching_interface_pins = set(
                connection.interface_pin_id
                for connection in db_ancillary.connections.all()
            )
            possible_pin_assignments = [
                pin_assignment
                for pin_assignment in interface.pin_assignments
                if pin_assignment.interface_pin.id in matching_interface_pins
            ]

            pin_assignments = []
            for connection in connections:
                if connection.pin_assignment:
                    # Connection specified as specific pin assignment
                    pin_assignments.append(connection.pin_assignment)
                else:
                    # Connection doesn't specify a specific pin assignment, pick the first one
                    pin_assignments.append(possible_pin_assignments[0])

            return cls(
                id=db_ancillary.id,
                component_reference=reference,
                ancillary_type=db_ancillary.ancillary_type,
                applies_to=db_ancillary.applies_to,
                connection_type=db_ancillary.connection_type,
                connections=connections,
                parent=parent,
                interface=interface,
                maximum_latency=db_ancillary.maximum_latency,
            )
        elif db_ancillary.applies_to == AncillaryAppliesTo.pins and parent:
            return cls(
                id=db_ancillary.id,
                component_reference=reference,
                ancillary_type=db_ancillary.ancillary_type,
                applies_to=db_ancillary.applies_to,
                connection_type=db_ancillary.connection_type,
                connections=connections,
                parent=parent,
                interface=None,
                maximum_latency=db_ancillary.maximum_latency,
            )
        raise RuntimeError(
            f"Can't create a {db_ancillary.applies_to} ancillary without an interface/bus/parent!"
        )

    @staticmethod
    def get_ancillary_block(
        db_ancillary: models.Ancillary,
        optimization_weights: Optional[Dict[str, float]] = None,
    ) -> models.Block:
        """Fetch an ancillary's block."""

        if optimization_weights is None:
            optimization_weights = {}

        cost_func = (
            reduce(
                add,
                [
                    v * Cast(KeyTextTransform(k, "attributes"), FloatField())
                    for k, v in optimization_weights.items()
                ],
            )
            if len(optimization_weights) > 0
            else Value(0, FloatField())
        )

        block = (
            query.blocks(
                category=db_ancillary.get_category(),
                attribute_queries=[
                    query.AttributeQuery.from_attribute_encoded(
                        attribute.attribute_definition,
                        operator=query.AttributeQuery.Operator(attribute.operator),
                        value=attribute.value,
                    )
                    for attribute in db_ancillary.attributes.all()
                ],
                connectivity=db_ancillary.connectivity,
            )
            .annotate(cost_func=cost_func)
            .order_by("cost_func")
            .first()
        )

        if not block:
            raise RuntimeError(f"Couldn't find ancillary block for {db_ancillary}")
        return cast(models.Block, block)

    def matches(
        self,
        interface_pin_id: Optional[UUID],
        pin_id: UUID = None,
        bus: Bus = None,
        interface: ComponentInterface = None,
    ) -> bool:
        """Returns whether this ancillary matches the given set of objects.

        - A bus ancillary will match if its bus and interface pin match.
        - An interface ancillary will match if its interface and interface pin match.
        - Pin ancillaries will match if the given pin matches.
        Other future ancillaries might match on other criteria.

        interface_pin_id and pin are mutually exclusive - pin ancillaries don't have interface_pin_ids and vice versa.
        """
        if len([t for t in [pin_id, bus, interface] if t]) != 1:
            raise RuntimeError(
                "Ancillary.matches expects exactly one of bus/interface/pin!"
            )
        if interface_pin_id and pin_id or not pin_id and not interface_pin_id:
            raise RuntimeError(
                "Exactly one of pin or interface_pin_id should be passed!!"
            )

        if interface_pin_id and not any(
            interface_pin_id == connection.interface_pin_id
            for connection in self.connections
        ):
            return False

        # Bus ancillaries apply to a specifc bus
        if bus and self.bus == bus:
            return True

        # Interface ancillaries apply to a specific component interface
        if interface and self.interface == interface:
            return True

        # Pin ancillaries apply to a specific set of pins
        if pin_id and pin_id in (connection.pin_id for connection in self.connections):
            return True

        return False

    def apply(self, ancillary_component: "Component") -> AppliedConnection:
        """Apply all the connections of this ancillary.

        Returns a single AppliedConnection object containing all the connection and mask information."""
        assert (
            ancillary_component.ancillary == self
        ), "Ancillary.apply got an unrelated ancillary component!"

        combined_connections = AppliedConnection(pin_connections=set(), pin_mask={})

        for connection in ancillary_component.ancillary.connections:
            applied_connection = connection.apply(ancillary_component)
            combined_connections.pin_mask.update(applied_connection.pin_mask)
            combined_connections.pin_connections.update(
                applied_connection.pin_connections
            )

        return combined_connections

    @property
    def ordering(self) -> Tuple[float, int]:
        """Return an ordering for an ancillary that can be used as a key function for sorting.

        This first sorts ancillaries by their timing constraint so all ancillaries with timinig constraints come first,
        then by the general ancillary ordering which specifies which types go in what order (series before parallel)
        """
        # For ancillaries with no timinig constraint, just set a very high timing constraint§
        maximum_latency = self.maximum_latency or float("inf")
        return (maximum_latency, _ancillary_ordering(self))

    @property
    def parent_pins(self) -> List[ComponentPin]:
        """Get all the pins on the parent component this ancillary connects to."""
        if not self.parent:
            # Bus ancillaries have no parent pins
            return []
        if self.applies_to == AncillaryAppliesTo.interface:
            assert self.interface
            pins = set()
            for connection in self.connections:
                if not connection.interface_pin_id:
                    raise RuntimeError(
                        f"Connection {connection} has no interface pin id, that should never happen!"
                    )
                # For each pin assignment, add only those pins that belong to the pin assignment that are active.
                # Note there are scenarios where this isn't 100% exact, but they should not cause any issues.
                # To do this 100% accurately, we'd have to store which active pins belong to which pin assignment.
                pins |= self.interface.active_pins(
                    interface_pin_id=connection.interface_pin_id,
                    pin_assignment=connection.pin_assignment,
                )
            return list(pins)
        elif self.applies_to == AncillaryAppliesTo.pins:
            return [
                self.parent.get_pin(connection.pin_id)
                for connection in self.connections
                if connection.pin_id
            ]
        raise NotImplementedError(
            f"parent_pins not yet implement for {self.applies_to}"
        )
