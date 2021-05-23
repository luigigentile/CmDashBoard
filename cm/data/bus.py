from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, List, Set

from cm.data.bus_fragment import BusFragment
from cm.data.component_interface import ComponentInterface
from cm.data.component_pin import ComponentPin
from cm.data.interface_family import InterfaceFamily
from cm.data.interface_pin import InterfacePin

if TYPE_CHECKING:
    from cm.data.component import Component  # noqa (needed for type checking)
    from cm.data.component import ComponentFilter  # noqa (needed for type checking)


@dataclass(frozen=True, order=True)
class Bus:
    """A Bus on a concrete component (part or sub-circuit) in a circuit."""

    fragments: List[BusFragment]

    def __str__(self) -> str:
        return f"{self.interface_family().label} on {', '.join(i.name for i in self.interfaces)}"

    def interface_family(self) -> InterfaceFamily:
        """Get the interface family for this bus.

        All interfaces of a bus are expected to belong to the same family.
        Empty buses get a special family.
        """
        # Special case for empty buses
        if not self.fragments:
            return InterfaceFamily(
                id=None, name="Do not connect", label="DNC", interface_types=[]
            )

        families = set(
            interface.interface_type.family for interface in self.physical_interfaces
        )

        if len(families) > 1:
            interface_labels = [
                f"{interface.component.reference}.{interface.name}"
                for interface in self.interfaces
            ]
            raise RuntimeError(
                f"Bus on {', '.join(interface_labels)} has more than one family, this is not supported! "
                f"Families were: {', '.join([str(f) for f in families])}"
            )

        return families.pop()

    @property
    def reference(self) -> str:
        """Fragments only get added if they have the same reference, so we can just pick any fragment's reference."""
        if not self.fragments:
            return ""
        return self.fragments[0].reference

    def __hash__(self) -> int:
        return hash(self.reference)

    def __eq__(self, other: object) -> bool:
        """Buses are equal if they have any fragments in common."""
        if not isinstance(other, Bus):
            return False
        return len(set(self.fragments) & set(other.fragments)) > 0

    # Fragments - source/target/both
    @property
    def source_fragments(self) -> Set[BusFragment]:
        """The set of fragments that the bus originates from.

        These are all fragments that have a physical (is_part) from_component.
        """
        return set(
            fragment for fragment in self.fragments if fragment.from_component.is_part
        )

    @property
    def target_fragments(self) -> Set[BusFragment]:
        """The set of fragments that the bus targets.

        These are all fragments that have a physical (is_part) to_component.
        """
        return set(
            fragment for fragment in self.fragments if fragment.to_component.is_part
        )

    @property
    def physical_fragments(self) -> Set[BusFragment]:
        """The set of all fragments in the bus that have physical from- or to-components."""
        return self.source_fragments | self.target_fragments

    # Components - source/target/both
    @property
    def source_components(self) -> Set["Component"]:
        """Return the set of all components this bus originates at."""

        return set(fragment.from_component for fragment in self.source_fragments)

    @property
    def target_components(self) -> Set["Component"]:
        """Return the set of all components this bus goes to."""

        return set(fragment.to_component for fragment in self.target_fragments)

    @property
    def physical_components(self) -> Set["Component"]:
        """Return the set of all physical components contained in this bus."""
        return self.source_components | self.target_components

    # Interfaces - all/source/target/both

    @property
    def interfaces(self) -> Set[ComponentInterface]:
        """The set of all interfaces (physical or sub-circuit) this bus contains."""
        all_interfaces = set()
        for fragment in self.fragments:
            if fragment.from_interface:
                all_interfaces.add(fragment.from_interface)
            if fragment.to_interface:
                all_interfaces.add(fragment.to_interface)
        return all_interfaces

    @property
    def source_interfaces(self) -> Set[ComponentInterface]:
        """Return the set of all physical interfaces this bus originates at."""
        return set(
            fragment.from_interface
            for fragment in self.source_fragments
            if fragment.from_interface
        )

    @property
    def target_interfaces(self) -> Set[ComponentInterface]:
        """Return the set of all physical interfaces this bus goes to."""
        return set(
            fragment.to_interface
            for fragment in self.target_fragments
            if fragment.to_interface
        )

    @property
    def physical_interfaces(self) -> Set[ComponentInterface]:
        """Return the set of all physical interfaces contained in this bus."""
        return self.source_interfaces | self.target_interfaces

    # Interface pins - source/target/both
    @property
    def source_interface_pins(self) -> Set[InterfacePin]:
        """The set of interfaces pins assigned to the bus on the physical components it originates from."""
        interface_pins = set()
        for fragment in self.source_fragments:
            interface_pins |= fragment.from_interface_pins

        return interface_pins

    @property
    def target_interface_pins(self) -> Set[InterfacePin]:
        """The set of interfaces pins assigned to the bus on the physical components it targets."""
        interface_pins = set()
        for fragment in self.target_fragments:
            interface_pins |= fragment.to_interface_pins

        return interface_pins

    @property
    def physical_interface_pins(self) -> Set[InterfacePin]:
        """The set of all interface pins on physical components on this bus."""
        return self.source_interface_pins | self.target_interface_pins

    # Pins - source/target/both
    @property
    def source_pins(self) -> Set[ComponentPin]:
        """The set of component pins assigned to the bus on the physical components it originates from."""
        pins: Set[ComponentPin] = set()
        for interface in self.source_interfaces:
            pins |= interface.active_pins()
        return pins

    @property
    def target_pins(self) -> Set[ComponentPin]:
        """The set of component pins assigned to the bus on the physical components it targets."""
        pins: Set[ComponentPin] = set()
        for interface in self.target_interfaces:
            pins |= interface.active_pins()
        return pins

    @property
    def physical_pins(self) -> Set[ComponentPin]:
        """The set of all component pins assigned to physical components on this bus."""
        return self.source_pins | self.target_pins

    def _reverse_connections(self) -> Dict[ComponentPin, Set[ComponentPin]]:
        """The superset of the reverse connections of all bus fragments of this bus."""
        reverse_connections: Dict[ComponentPin, Set[ComponentPin]] = defaultdict(set)

        for fragment in self.fragments:
            for from_pin, to_pins in fragment.reverse_connections.items():
                reverse_connections[from_pin] |= to_pins

        return reverse_connections

    def source_pins_for_pin(self, pin: ComponentPin) -> Set[ComponentPin]:
        """Get the set of source pins for a specific pin on this bus.

        Note that while this is mostly meant to be used to find the source of a specific target pin,
        it also works when passing in pins from any subcircuits in the bus.
        """
        all_reverse_connections = self._reverse_connections()

        # Traverse the graph created by the connections to find the source pins
        # Start with the specified target pin and go back through its connection until we find
        # pins that aren't the "from" of any other connections.
        pins_to_check = {pin}
        source_pins = set()
        while pins_to_check:
            next_pins_to_check = set()
            for to_pin in pins_to_check:
                if to_pin in all_reverse_connections:
                    # This pin is the "to" side of another connection, check its from pin
                    next_pins_to_check |= all_reverse_connections[to_pin]
                else:
                    # This pin doesn't show up as a "to" in any connection, it's a source pin.
                    source_pins.add(to_pin)
            pins_to_check = next_pins_to_check

        return source_pins
