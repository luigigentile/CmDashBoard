from collections import namedtuple
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Dict, FrozenSet, List, Optional, Sequence, Set
from uuid import UUID

import networkx as nx

from cm.data.interface_pin import InterfacePin
from cm.db import models

Node = namedtuple("Node", ["pin", "is_requesting"])

if TYPE_CHECKING:
    from cm.data.interface_type import InterfaceType


@dataclass(frozen=True)
class LogicalNetwork:
    """A helper class representing a logical network within an interface family.

    A logical network is a set of mutually compatible pins which can form a logical net, and after adding ancilliaries
    a number of nets in a circuit.

    The network is made up of requesting pins, which (arbitrarily) are the pins the connection originates from,
    and receiving pins. Note that these distinctions purely exist in logic, they have nothing to do with the direction
    of data flow.
    """

    requesting_pins: FrozenSet[InterfacePin]
    receiving_pins: FrozenSet[InterfacePin]

    @classmethod
    def from_nodes(self, nodes: Sequence[Node]) -> "LogicalNetwork":
        """Create a logical network from a set of connected graph nodes."""
        requesting_pins = set()
        receiving_pins = set()
        for node in nodes:
            if node.is_requesting:
                requesting_pins.add(node.pin)
            else:
                receiving_pins.add(node.pin)
        return LogicalNetwork(frozenset(requesting_pins), frozenset(receiving_pins))

    @property
    def name(self) -> str:
        requesting_pin_references = set(p.reference for p in self.requesting_pins)
        receiving_pin_references = set(p.reference for p in self.receiving_pins)
        return f"{', '.join(requesting_pin_references)} -> {', '.join(receiving_pin_references)}"

    @property
    def pins(self) -> FrozenSet[InterfacePin]:
        return self.requesting_pins | self.receiving_pins


@dataclass(unsafe_hash=True)
class InterfaceFamily:
    """Analogous class to cm.db.models.InterfaceFamily."""

    id: Optional[UUID]  # id of the corresponding model object
    name: str
    label: str
    interface_types: List["InterfaceType"] = field(
        hash=False, repr=False, compare=False
    )

    @classmethod
    def _from_db(cls, db_family: models.InterfaceFamily,) -> "InterfaceFamily":
        """Private method for creating interface families from db instances.

        This method, unlike most other from_db methods, isn't meant to be used directly.
        This is because families are linked closely to the interface types they contain,
        so it it much more efficient to always create and then cache all families along with their types.

        To get an interface family from a db object, just run

        InterfaceFamily.get_all(as_dict=True)[db_family.id]
        """

        return cls(
            id=db_family.id,
            name=db_family.name,
            label=db_family.label,
            interface_types=[],  # gets populated afterwards
        )

    def __str__(self) -> str:
        return self.name

    def _pin_graph(self) -> nx.Graph:
        """Internal helper to create a graph of interface pins showing which pins are compatible.

        This splits the pins into requesting and receiving pins, which is important for uniquely identifying
        the logical networks. """
        # We can get the set of possible logical networks by connecting all interface pins from this family in a graph
        # with edges between all compatible pins. For every pin of all family types with `can_be_required` set to True,
        # we create an outgoing edge.
        interface_pins: Set[InterfacePin] = set()
        for interface_type in [t for t in self.interface_types if t.can_be_required]:
            interface_pins |= set(interface_type.pins)

        # A graph where the nodes are interface type pins.
        # The connected components of this graph are the basis of the logical networks
        pin_graph = nx.Graph()

        for requesting_pin in interface_pins:
            # Add edges for all compatible pins, from the requesting to the receiving pin
            for compatible_pin in requesting_pin.compatible_pins:
                pin_graph.add_edge(
                    Node(requesting_pin, True), Node(compatible_pin, False),
                )

        return pin_graph

    def get_logical_networks(self) -> Dict[str, LogicalNetwork]:
        """Return all the logical networks that can make up a bus of this interface family.

        * A logical network is each group of interface pins that are connected together, ignoring ancillary.
        For example, in a SPI bus with 2 slaves and one master, there might be one logical network
        consisting of all SCK pins.
        """

        networks = {}

        for connected_nodes in nx.connected_components(self._pin_graph()):
            network = LogicalNetwork.from_nodes(connected_nodes)
            networks[network.name] = network

        return networks

    def get_logical_network(
        self, interface_pin: InterfacePin, is_requesting: bool = True
    ) -> LogicalNetwork:
        """Returns the logical network that the specified pin belongs to.

        Defaults to treating the pin as the requesting pin,
        use is_requesting=False to get a receiving pin's logical network.

        Note that it's important to specify whether the pin is requesting or receiving,
        as just specifying any pin on the logical network would allow for some uncertainty on symmetric interfaces,
        like RX/TX on uart, which represent two different logical networks depending on which pin is the requesting one
        (RX -> TX or TX -> RX).

        """

        pin_graph = self._pin_graph()

        # In the pin graph, find the connected component that contains the pin.
        # This will form the pin's logical network.
        for connected_nodes in nx.connected_components(pin_graph):
            for node in connected_nodes:
                if node.is_requesting != is_requesting:
                    continue
                if node.pin == interface_pin:
                    return LogicalNetwork.from_nodes(connected_nodes)

        raise KeyError(
            f"Could not find logical network for {'requesting' if is_requesting else 'receiving'} pin {interface_pin}!"
        )

    @staticmethod
    def get_all() -> List["InterfaceFamily"]:
        """Heavily cached helper function for the frequently needed task of getting all interface families."""
        from cm.data.interface_type import InterfaceType

        # Get all interfacd types - we construct the families when constructing the types as well,
        # so we just get them from there. Both functions are heavily cached, so it's more effective to just
        # fetch the generated families via the types instead of creating them twice.
        interface_types = InterfaceType.get_all()

        interface_families: List["InterfaceFamily"] = []
        for interface_type in interface_types:
            if interface_type.family.id in interface_families:
                continue

            interface_families.append(interface_type.family)

        return interface_families

    @property
    def interface_pin_dict(self) -> Dict[UUID, InterfacePin]:
        return {
            interface_pin.id: interface_pin
            for interface_type in self.interface_types
            for interface_pin in interface_type.pins
        }
