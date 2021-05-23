from collections import defaultdict
from dataclasses import dataclass, field
from functools import cached_property
from itertools import combinations, groupby
from typing import Dict, FrozenSet, Iterator, List, Optional, Set, Tuple, cast
from uuid import UUID, uuid4

import networkx as nx

from cm.data.ancillary import Ancillary
from cm.data.bus import Bus
from cm.data.component import Component
from cm.data.component_interface import ComponentInterface
from cm.data.component_pin import ComponentPin
from cm.data.interface_family import LogicalNetwork
from cm.data.interface_pin import InterfacePin
from cm.data.interface_type import InterfaceType
from cm.data.spec import Spec
from cm.db.constants import AncillaryAppliesTo, AncillaryConnectionRole, BusSharing


class SmartNetlistError(Exception):
    pass


def _net_ordering(net: "SmartNet") -> Tuple[bool, str]:
    """Determines the order of nets in the netlist, to be used as a key function when sorting."""
    return (
        len(net.pins) == 0,  # empty nets come last in the file
        net.net_name_template,  # Rest is sorted alphabetically by net name
    )


def _pin_ordering(pin: ComponentPin) -> Tuple[str, str]:
    """Determines the order of pins within a net."""
    return (pin.pin.number, pin.pin.name)


@dataclass(frozen=True)
class SmartNet:
    pins: FrozenSet[ComponentPin]
    bus: Bus
    board: Optional[Component]

    @cached_property
    def non_ancillary_pins(self) -> FrozenSet[ComponentPin]:
        """Return the non-ancillary pins that belong to this net.

        Non-ancillary pins can show up directly in self.pins if the net is directly connected to a component,
        or they can be the pin.component.ancillary.parent_pin of a connection pin.
        """
        bus_pins = self.bus.physical_pins
        pins = set()
        for pin in self.pins:
            if not pin.component.ancillary:
                pins.add(pin)
            else:
                # Only add pins connected via ancillaries if their parent pins actually belong to this bus.
                # Even though a pin belongs to a net, its ancillary can still belong to a different bus, and we
                # need to compensate for that here (an example would be the second pin on a pull-up resistor. The pin
                # belongs to the VCC net, but the ancillary itself belongs to the bus that contains the pull-up.
                pins.update(
                    pin
                    for pin in pin.component.ancillary.parent_pins
                    if pin in bus_pins
                )
        return frozenset(pins)

    @cached_property
    def logical_network(self) -> LogicalNetwork:
        interface_family = self.bus.interface_family()

        # We can use any non-ancillary pin to determine the logical network,
        # as by definition all source pins of this net have to belong to the same logical network.
        non_ancillary_pin = list(self.non_ancillary_pins)[0]

        # To get the logical net we need to know whether this is a requesting pin or not.
        # It's a requesting pin if it's part of a source component.
        is_requesting = non_ancillary_pin.component in self.bus.source_components
        interface_pin = non_ancillary_pin.component.get_assigned_interface_pin(
            non_ancillary_pin
        )
        if not interface_pin:
            # There should always be an assigned interface pin, this is purely defensive and for typing
            raise RuntimeError(
                f"Could not determine a logical net for smart net {self}"
            )
        return interface_family.get_logical_network(
            interface_pin, is_requesting=is_requesting
        )

    @property
    def is_shared(self) -> bool:
        # If any interface pins in this net are shared, then this is a shared net.
        # Shared nets are named more broadly, not containing the requesting component for example.
        return any(
            interface_pin.sharing == BusSharing.shared
            for interface_pin in self.logical_network.pins
        )

    @property
    def interface_pin_label(self) -> str:
        """Get the interface pin label of the alphabetically first interface pin of this net's logical network."""
        return sorted(
            interface_pin.reference
            for interface_pin in self.logical_network.requesting_pins
        )[0]

    @property
    def source_pin(self) -> ComponentPin:
        """Return the source pin for a non-shared net.

        Calling this on a shared net will raise an exception."""

        if self.is_shared:
            raise RuntimeError("source_pin called for shared net, this is not allowed!")

        # When looking at the source pins we need to exclude ancillary pins carefully.
        # This is because ancillary pins can show up in unexpected places and break the assumption that a non-shared
        # net only has two pins on it.
        source_pins: Set[ComponentPin] = set()
        for pin in self.non_ancillary_pins:
            pin_source_pins = self.bus.source_pins_for_pin(pin)
            source_pins.update(
                source_pin
                for source_pin in pin_source_pins
                if not source_pin.component.ancillary
            )

        if not source_pins:
            raise RuntimeError(f"Could not find a source pin for {self}!")

        # There could be several source pins attached to this net, and we need a consistent name
        # so we simply sort the pins by their name and use the first one.
        return sorted(source_pins, key=lambda component_pin: component_pin.pin.name)[0]

    @cached_property
    def identifier(self) -> str:
        """The net identifier determines whether a net is the only one of its kind, or whether it needs an index.

        For shared nets, a net needs an index if there is more than one bus of its family.
            (SPI vs SPI0 and SPI1)
        For non-shared nets, a net needs an index if there is more than one component with the same function.
            (LED vs LED1 and LED2)

        For clarity - An index is applied to the net name template if the same template is shared by multiple nets
        with _different_ identifiers.
        """
        if len(self.pins) == 1:
            # Unconnected pins will always be separate and never need indexing, so they get a unique reference.
            return str(uuid4())

        if self.is_shared:
            # Shared nets are identified only by their bus (SPI or SPI0 or SPI1)
            # Everything that's on the same bus will have the same identifier, and share an index
            return self.bus.reference

        # Non-shared nets are identified by the originating component (LED or LED1 or LED2)
        # Any net with the same template (LED<index>_A) will get indexed if the source component is different.
        source_pin = self.source_pin
        return f"{source_pin.component.reference}"

    @cached_property
    def net_name_template(self) -> str:
        # Nets with only one pin aren't really nets, and so get an empty name
        if len(self.pins) == 1:
            return ""

        if self.is_shared:
            # Shared buses are formatted as
            # <interface_family_label><index>_<interface_pin_reference>
            # the interface pin is only added if the bus's interface family has more than one logical network
            bus_label = f"{self.bus.interface_family().label}<index0>"
            if len(self.bus.interface_family().get_logical_networks()) == 1:
                return bus_label

            return "_".join([bus_label, self.interface_pin_label.upper(),])

        # Non-shared buses are formatted as
        # <from_component_function><index>_<pin_name>

        # NOTE: There is one unsupported special case here, which is the case of multiple pins having the same name
        # but being used in different nets. In cases like that we need to index the pin names.

        return f"{self.source_pin.component.function.upper()}<index1>_{self.source_pin.pin.name.upper()}"

    @property
    def sorted_pins(self) -> List[ComponentPin]:
        return sorted(self.pins, key=_pin_ordering)

    @property
    def interface_pins(self) -> Set[InterfacePin]:
        """Helper to get the interface pins involved in this smart net."""
        interface_pins: Set[InterfacePin] = set()
        pin_ids = defaultdict(set)

        # Needed to check if an ancillary connection applies to this net
        for pin in self.pins:
            pin_ids[pin.component.component_id].add(pin.pin.id)

        # The smart net might not be connecting straight to any "real" interface pins because of ancillaries,
        # but we can find out the connected interface pins by going through the ancillary's parent pin.
        non_ancillary_pins: Set[ComponentPin] = set()

        for component in self.components:
            if component.ancillary:
                if component.ancillary.applies_to == AncillaryAppliesTo.bus:
                    # Bus ancillaries are always parallel, so ignore them (the parent pin will also be in the net)
                    continue

                non_ancillary_pins |= {
                    input_pin
                    for connection in component.ancillary.connections
                    for input_pin in connection.input_pins(component.ancillary)
                    if input_pin
                    and connection.role == AncillaryConnectionRole.input
                    and connection.ancillary_pin_id in pin_ids[component.component_id]
                }
            else:
                # This non-ancillary component is directly connected to the net
                non_ancillary_pins |= {
                    pin for pin in self.pins if pin.component == component
                }

        for pin in non_ancillary_pins:
            assigned_interface_pin = pin.component.get_assigned_interface_pin(pin)
            if assigned_interface_pin:
                interface_pins.add(assigned_interface_pin)
        return interface_pins

    @property
    def components(self) -> Set[Component]:
        return set(pin.component for pin in self.pins)

    @cached_property
    def is_global(self) -> bool:
        """Check whether a net is global (outside of component-based series ancillaries).

        We can determine this by checking for all the non-ancillary components this net involves, via
            - directly being connected to the net
            - a connected ancillary's parent

        If the net involves more than one non-ancillary component, then it's a global net.
        """
        non_ancillary_components = set()

        for component in self.components:
            if not component.ancillary:
                # This component is directly connected to the net
                non_ancillary_components.add(component)
            else:
                # This component is connected via an ancillary
                non_ancillary_components.update(
                    pin.component for pin in component.ancillary.parent_pins
                )

        return len(non_ancillary_components) > 1

    def show(self) -> None:
        """Print a human-readable representation of this smart net."""
        components = set(pin.component for pin in self.pins)
        for component in sorted(components, key=lambda c: c.reference):
            component_pins = [pin for pin in self.pins if pin.component == component]
            print(f"{component.reference}")
            for pin in component_pins:
                pin_interfaces = [
                    interface.name
                    for interface in component.active_interfaces
                    if pin in interface.active_pins()
                ]
                print(f"\t{pin} (interfaces: {', '.join(pin_interfaces)})")


@dataclass
class SmartNetlist:
    spec: Spec
    nets: Set[SmartNet] = field(default_factory=set)

    # This dictionary keeps track of pins that are masked by ancillaries through series connections.
    # If a component's pin A is exposed via pin 2 of a resistor, this would look like:
    # {IC1.A: R1.2} ({original_pin: exposed_pin})
    pin_mask: Dict[ComponentPin, ComponentPin] = field(default_factory=dict)

    # Essentially the reverse of pin mask, but keeps a record of all original pins that are masked by pins.
    # In pin-mask, only the outermost output pin is visibile, but this dictionary allows reconstructing where every
    # pin comes from.
    original_pins: Dict[ComponentPin, ComponentPin] = field(default_factory=dict)

    # To figure out which pins should go on the same nets, we use a graph with pins as nodes.
    # We add connections between the pins if those pins are connected together, and then use
    # connected components to find the groups of pins that should be in the same net, then create a net
    # object for these pins.
    # NOTE: a bus can consist of many nets, but a net can never contain more than one bus
    pin_graph: nx.Graph = field(default_factory=lambda: nx.Graph())  # type: ignore

    def nets_by_bus(self) -> Iterator[Tuple[Optional[Bus], Iterator[SmartNet]]]:
        return groupby(
            sorted(self.nets, key=lambda net: net.bus),
            lambda net: net.bus if net.bus.fragments else None,
        )

    def pins_by_net(self) -> Iterator[Tuple[SmartNet, ComponentPin]]:
        for net in sorted(self.nets, key=_net_ordering):
            for pin in net.pins:
                yield net, pin

    def components(self) -> Set[Component]:
        return {pin.component for net in self.nets for pin in net.pins}

    def ordered_nets(self, board: Optional[Component]) -> List[SmartNet]:
        return sorted(
            [net for net in self.nets if net.board == board], key=_net_ordering,
        )

    def nets_by_template(self, board: Optional[Component]) -> Dict[str, List[SmartNet]]:
        net_templates: Dict[str, List[SmartNet]] = defaultdict(list)
        for net in self.ordered_nets(board):
            net_templates[net.net_name_template].append(net)
        return net_templates

    def _global_net_name(self, net: SmartNet) -> str:
        """Calculate the global net name of the given smart net.

        This is the net name without the _S suffix for series ancillary nets.
        """

        # The biggest challenge in naming nets is to figure out if multiple nets have the same format
        # and so need to be indexed. (VCC vs VCC0 and VCC1, or LED_ANODE vs LED0_ANODE and LED1_ANODE)
        # We figure this out by getting the net's net name template, which is its net name with a
        # placeholder for the index.
        # If more than one net with the same template has a different identifier, then we add the index of the net.
        # Note: this relies on self.nets_by_template using the nets in a consistent order.

        template = net.net_name_template

        # Get all nets with the same _template_, and get their identifiers
        identifiers = set()
        for candidate_net in self.nets_by_template(net.board)[template]:
            identifiers.add(candidate_net.identifier)

        # The conflicting nets are all of these nets taken together
        conflicting_identifiers = sorted(identifiers)

        # Sanity check - the current net should always be in the generated list of nets with the same template
        if net.identifier not in conflicting_identifiers:
            raise RuntimeError(
                "Unexpected error in _global_net_name, net doesn't appear under the expected identifier"
            )

        # Note the index is completely arbitrary (because references are arbitrary), but stable
        index: Optional[int]
        if len(identifiers) > 1:
            index = conflicting_identifiers.index(net.identifier)
        else:
            index = None

        # We can now establish the global net name from the template and the optional index.
        template = template.replace(
            "<index0>", str(index) if index is not None else ""
        )  # 0-based index (for buses/interfaces)
        template = template.replace(
            "<index1>", str(index + 1) if index is not None else ""
        )  # 1-based index (for parts)
        return template

    def net_name(self, net: SmartNet) -> Optional[str]:
        """Return the net name of a net belonging to this netlist."""
        # Nets with only one pin aren't really nets, and so get an empty name
        if len(net.pins) == 1:
            return None

        net_names = self.nets_by_global_net_name
        reverse_nets = {
            _net: net_name for net_name, nets in net_names.items() for _net in nets
        }

        global_net_name = reverse_nets[net]

        # If the net is a global net, simply return the global net name
        if net.is_global:
            return global_net_name

        # For local nets, add an additional suffix differentiating the different serial ancillary nets
        # We can do this simply by using the index of this net vs other nets with the same global net name.

        # Get all nets that have the same global name
        # IMPORTANT: the nets here have to be ordered, so we can use the index in this list to determine the suffix!
        nets_with_same_global_name: List[SmartNet] = []
        for ordered_net in self.ordered_nets(net.board):
            if reverse_nets[ordered_net] == global_net_name:
                nets_with_same_global_name.append(ordered_net)

        # Note: we do have to exclude the global net here to make sure the indexes are correct
        related_local_nets = [
            related_net
            for related_net in nets_with_same_global_name
            if not related_net.is_global
        ]

        # If there are multiple local nets with the same template, index them with _S<index>
        if len(related_local_nets) > 1:
            return f"{global_net_name}_S{related_local_nets.index(net)}"
        # If there is only one, just use the suffix _S
        return f"{global_net_name}_S"

    @cached_property
    def nets_by_global_net_name(self) -> Dict[str, List[SmartNet]]:
        nets = defaultdict(list)
        for net in self.nets:
            nets[self._global_net_name(net)].append(net)
        return nets

    def show(self) -> None:
        """Print a human-readable representation of this smart netlist."""
        for net in self.nets:
            print(f"Net {net}")
            net.show()
            print("")

    @cached_property
    def interface_types(self) -> Dict[UUID, InterfaceType]:
        return InterfaceType.get_all_as_dict()

    def get_ancillary_components(self) -> List[Component]:
        """Return all ancillary components in the circuit."""
        return [
            candidate_component
            for _, candidate_component in self.spec.root_component.iterate_parts()
            if candidate_component.ancillary
        ]

    def connect_local_ancillaries(self) -> None:
        """Apply the connections for all local (non-bus) ancillaries.

        Note: connecting bus and local ancillaries is split, because the bus ancillaries need to have all interfaces
        fully connected before they can be applied
        """
        ancillary_components = self.get_ancillary_components()
        non_bus_ancillary_components = sorted(
            [
                ancillary_component
                for ancillary_component in ancillary_components
                if ancillary_component.ancillary
                and ancillary_component.ancillary.applies_to != AncillaryAppliesTo.bus
            ],
            key=lambda component: cast(  # these are all guaranteed to have ancillaries
                Ancillary, component.ancillary
            ).ordering,
        )

        for ancillary_component in non_bus_ancillary_components:
            assert ancillary_component.ancillary

            applied_ancillary_connections = ancillary_component.ancillary.apply(
                ancillary_component
            )

            # Now that all connections are processed, first add the connected pins to the pin graph
            # (using the current global pin mask to account for output from previous ancillaries)
            for pin1, pin2 in applied_ancillary_connections.pin_connections:
                self.pin_graph.add_edge(
                    self.pin_mask.get(pin1, pin1), self.pin_mask.get(pin2, pin2)
                )
            # Only after processing the connections, update the pin mask with the newly masked pins from this ancillary.
            # The reason for this order is that if an ancillary masks an input pin, this ancillary itself
            # should still reference the original pin, not the masked one.
            self.pin_mask.update(applied_ancillary_connections.pin_mask)
            for (
                original_pin,
                output_pin,
            ) in applied_ancillary_connections.pin_mask.items():
                self.original_pins[output_pin] = original_pin

    def get_logical_network(
        self,
        interface: ComponentInterface,
        interface_pin: InterfacePin,
        is_requesting: bool,
    ) -> LogicalNetwork:
        try:
            logical_network = interface.interface_type.family.get_logical_network(
                interface_pin, is_requesting=is_requesting
            )
        except KeyError:
            # HACK: Until we have "proxy" bus fragments we will have situations where a bus fragment
            # goes between two incompatible interface types (e.g. I2C Slave -> I2C Slave). This means
            # we can't find a valid logical network for an interface pin.
            # For now, we just look for one logical network on the interface that has the interface pin.
            # If no logical networks, or more than one logical network, match then we raise an error.
            logical_networks = [
                logical_network
                for logical_network in interface.interface_type.family.get_logical_networks().values()
                if interface_pin in logical_network.pins
            ]
            if len(logical_networks) < 1:
                raise KeyError(
                    f"Could not find any logical network for pin {interface_pin}!"
                )
            elif len(logical_networks) > 1:
                raise KeyError(
                    f"Found multiple logical networks for pin {interface_pin}!"
                )
            else:
                logical_network = logical_networks[0]

        return logical_network

    def connect_buses(self, flattened_buses: List[Bus]) -> None:
        """Connect up all active interfaces, making sure to take the local ancillary pin masks into account.

        Bus ancillaries are also applies in this step
        """
        for bus in flattened_buses:
            # For each bus, we keep track of the pins that belong to the same logical network
            # These all get connected together in the pin graph at the end.
            bus_pins_to_connect: Dict[LogicalNetwork, Set[ComponentPin]] = defaultdict(
                set
            )
            # Small helper to remember which rqeuesting interface pin belongs to which logical network
            interface_pin_map: Dict[LogicalNetwork, InterfacePin] = {}

            for interface in bus.physical_interfaces:
                # To determine the right logical net, we need to know the bus's direction in relation to this interface
                is_requesting = interface in bus.source_interfaces

                for interface_pin_id in interface.active_pin_uses.keys():
                    interface_pin = interface.interface_type.pin_dict[interface_pin_id]

                    logical_network = self.get_logical_network(
                        interface, interface_pin, is_requesting
                    )
                    if is_requesting:
                        interface_pin_map[logical_network] = interface_pin

                    # Add all active pins for this interface pin to the appropriate set of pins that need connecting
                    active_pins = interface.active_pins(interface_pin_id)
                    bus_pins_to_connect[logical_network].update(active_pins)

            # Connect bus ancillaries
            ancillary_components = self.spec.bus_ancillary_components(bus=bus)

            for logical_network, logical_network_pins in bus_pins_to_connect.items():
                requesting_interface_pin = interface_pin_map[logical_network]
                ancillary_components = self.spec.bus_ancillary_components(
                    bus=bus, interface_pin=requesting_interface_pin
                )

                # Apply only the connections that apply to the current logical network
                for ancillary_component in ancillary_components:
                    assert ancillary_component.ancillary
                    for connection in ancillary_component.ancillary.connections:
                        # Bus ancillaries exist only on interface pins (identifying a logical network)
                        if connection.interface_pin_id != requesting_interface_pin.id:
                            continue

                        applied_ancillary_connection = connection.apply(
                            ancillary_component, input_pins=logical_network_pins
                        )

                        for pin1, pin2 in applied_ancillary_connection.pin_connections:
                            self.pin_graph.add_edge(
                                self.pin_mask.get(pin1, pin1),
                                self.pin_mask.get(pin2, pin2),
                            )
                        self.pin_mask.update(applied_ancillary_connection.pin_mask)
                        for (
                            original_pin,
                            output_pin,
                        ) in applied_ancillary_connection.pin_mask.items():
                            self.original_pins[output_pin] = original_pin

                # Now that all involved pins for this bus are known, connect them all together.
                # NOTE: it's crucial to use the pin mask here, or local ancillaries will be bypassed
                for logical_network_pins in bus_pins_to_connect.values():
                    for pin1, pin2 in combinations(logical_network_pins, 2):
                        self.pin_graph.add_edge(
                            self.pin_mask.get(pin1, pin1),
                            self.pin_mask.get(pin2, pin2),
                        )

    def _create_nets(self, flattened_buses: List[Bus]) -> None:
        # Create a mapping of pins to buses to allow us to determine which bus each net belongs to
        buses_per_pin = {
            pin: bus for bus in flattened_buses for pin in bus.physical_pins
        }

        for pins in nx.connected_components(self.pin_graph):
            if len(pins) > 1:
                # These pins are part of a bus
                pin_buses = {
                    buses_per_pin[self.original_pins.get(pin, pin)]
                    for pin in pins
                    if pin in buses_per_pin
                }
                if not pin_buses:
                    self.spec.warnings.add(
                        f"Failed to connect pins {pins}, no bus could be found."
                    )
                    continue
                if len(pin_buses) > 1:
                    raise RuntimeError(
                        "Found set of pins belonging to more than one bus in smart netlist! "
                        "This should never happen."
                    )
                bus = pin_buses.pop()
            else:
                # This is a single unconnected pin - we'll create an empty bus for it.
                bus = Bus(fragments=[])

            # We want to have separate nets on each board (even though they logically connect together)
            # To accomplish that, we simply split the pins up by their component's board

            pins_by_board: Dict[Optional[Component], Set[ComponentPin]] = defaultdict(
                set
            )
            for connected_pin in pins:
                if not connected_pin.component.is_part:
                    raise RuntimeError(
                        "Found subcircuit pin in netlist, this should never happen!"
                    )
                pins_by_board[self.spec.board(connected_pin.component)].add(
                    connected_pin
                )

            for board, pins in pins_by_board.items():
                self.nets.add(SmartNet(pins=frozenset(pins), bus=bus, board=board))

    @classmethod
    def from_spec(cls, spec: Spec) -> "SmartNetlist":
        netlist = cls(spec=spec)
        flattened_buses = spec.root_component.flattened_buses()

        # We want all pins, even unconnected ones, to appear in the smart netlist. To make sure that's the case,
        # we first add all component pins to the pin graph as unconnected nodes.
        for _, part in spec.root_component.iterate_parts():
            for pin in part.pins:
                netlist.pin_graph.add_node(pin)

        # Connect the local ancillaries (all ancillaries except for bus ancillaries, which have to be connected later)
        netlist.connect_local_ancillaries()

        # Make the global connections - this will connect all interfaces on buses together, and apply their ancillaries.
        netlist.connect_buses(flattened_buses)

        # All information is now in the pin graph, so we can create the smart nets.
        netlist._create_nets(flattened_buses)

        return netlist

    def get_pin_nets(self, pin: ComponentPin) -> List[SmartNet]:
        """Return all nets that include a given component pin."""
        return [net for net in self.nets if pin in net.pins]
