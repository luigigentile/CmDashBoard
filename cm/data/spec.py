from collections import defaultdict
from dataclasses import dataclass, field
from functools import cached_property
from typing import Any, Dict, Iterable, Iterator, List, Optional, Set, Union, cast
from uuid import UUID

from pint.quantity import _Quantity

from cm.constants import DEFAULT_ARCHITECTURE
from cm.data import (
    bus,
    component,
    net,
    placement,
    ranges,
    schemas,
    serializable,
    smart_netlist,
    trace,
    units,
)
from cm.data.interface_pin import InterfacePin
from cm.data.layout import Layout
from cm.data.procurement_data import DistributorPart
from cm.db import models
from cm.db.constants import AncillaryAppliesTo
from cm.optimization.types import PickedOffer
from cm.settings import DEFAULT_MAIN_BOARD_REFERENCE

mm = units.UNITS("mm")


@dataclass(init=False, frozen=True)
class ConnectorsSpec(serializable.Serializable):
    type: Optional[str] = None
    series: Optional[str] = None
    pins: Optional[int] = None

    SCHEMA = schemas.CONNECTORS_SPEC_SCHEMA

    def __init__(self, connectors: Optional[Dict[str, Any]]):
        object.__setattr__(self, "type", connectors and connectors.get("type"))
        object.__setattr__(self, "series", connectors and connectors.get("series"))
        object.__setattr__(self, "pins", connectors and connectors.get("pins"))


@dataclass(init=False)
class Spec(serializable.Serializable):
    """A spec is the description of a circuit that is passed through various processing stages.

    At the beginning of the process, the spec is equivalent to the user input. Then, various
    processing stages take the spec and refine and constrain it more and more, until it represents
    a fully defined, manufacturable board.

    The idea behind this is that a very defined spec can be passed back to an earlier part in the
    processing pipeline for optimisation, making use of information gained later on in the process.
    """

    SCHEMA = schemas.SPEC_SCHEMA

    name: str
    number_of_boards: int
    maximum_price: float  # treating maximum price as unitless for now
    width: ranges.QuantityRange
    height: ranges.QuantityRange
    layers: ranges.NumberRange

    architecture_strategy: str  # The strategy used to resolve ambivalences in the spec definition

    root_component: component.Component

    schematics: Dict[str, List[UUID]]

    boards: Dict[str, List[UUID]]
    main_board_reference: Optional[str]
    connectors: ConnectorsSpec

    nets: List[net.Net]
    traces: List[trace.Trace]
    placements: Dict[str, placement.Placement]  #: Placement information per part

    layout: Layout

    optimization_weights: Dict[
        str, float
    ]  # Weights used in the cost function of the optimization algorithms

    warnings: Set[str]

    # Distributor parts are stored by block id
    distributor_parts: Dict[UUID, List[DistributorPart]] = field(
        default_factory=lambda: defaultdict(list), repr=False
    )

    # The original state of the spec, to allow comparision between the current state and the original requirements
    # FIXME: the implementation of this was removed because it requires a proper method of copying/serializing specs.
    _original: Optional["Spec"] = None

    def __init__(
        self,
        name: str,
        number_of_boards: int,
        maximum_price: float,
        width: ranges.QuantityRange,
        height: ranges.QuantityRange,
        layers: ranges.NumberRange,
        root_component: component.Component,
        schematics: Dict[str, List[UUID]],
        boards: Dict[str, List[UUID]],
        nets: List[net.Net],
        traces: List[trace.Trace],
        placements: Dict[str, placement.Placement],
        main_board_reference: str = None,
        connectors: Dict[str, Any] = None,
        architecture_strategy: str = None,
        optimization_weights: Dict[str, float] = None,
        warnings: Iterable[str] = None,
        distributor_parts: Dict[UUID, List[DistributorPart]] = None,
    ):
        self.name = name
        self.number_of_boards = number_of_boards
        self.maximum_price = maximum_price
        self.width = width
        self.height = height
        self.layers = layers
        self.root_component = root_component
        self.schematics = schematics
        self.boards = boards
        self.main_board_reference = main_board_reference or DEFAULT_MAIN_BOARD_REFERENCE
        self.connectors = ConnectorsSpec(connectors)
        self.nets = nets
        self.traces = traces
        self.placements = placements
        self.optimization_weights = optimization_weights or {}
        self.warnings = set(warnings or [])
        self.distributor_parts = distributor_parts or {}
        self.picked_offers: Dict[
            UUID, List[PickedOffer]
        ] = {}  # this will be filled in during _apply_solution with purchase information from solution

        self.architecture_strategy = architecture_strategy or DEFAULT_ARCHITECTURE

        # We sometimes have to construct an invalid spec, to be able to properly process validation errors.
        # One scenario that can happen is that the layers passed to the spec are invalid and are set to none.
        # In that case, we need to set them to some arbitrary value so that this constructor doesn't raise an exception.
        if self.layers:
            copper_layers = int(self.layers.low)
        else:
            copper_layers = 1

        # Create a layout - with the minimum number of layers specified to start.
        self.layout = Layout(copper_layers=copper_layers)

        # for each child of root_component, set parent to root_component
        for child in self.root_component.children:
            child.parent = self.root_component

    @property
    def price(self) -> float:
        """Calculate total spec price from the sum of its component's prices."""
        return sum(part.price for _, part in self.root_component.iterate_parts())

    @property
    def size(self) -> _Quantity:
        """Calculate total spec size from the sum of its component's sizes."""
        return sum(part.size for _, part in self.root_component.iterate_parts())

    @cached_property
    def netlist(self) -> "smart_netlist.SmartNetlist":
        """Get smart netlist for the spec."""
        return smart_netlist.SmartNetlist.from_spec(self)

    @cached_property
    def flattened_references(self) -> Dict[str, str]:
        """Get flattened component references for the spec."""
        if any(
            not isinstance(candidate, component.Component)
            for candidate in self.root_component.get_atomic_components()
        ):
            raise RuntimeError("flattened_references called on unresolved spec!")
        return self.root_component.flattened_references()

    def net_by_name(self, net_name: str) -> net.Net:
        """Get a net by name."""
        for n in self.nets:
            if n.name == net_name:
                return n
        raise KeyError(f"Unknown net {net_name}!")

    def net_index(self, n: net.Net) -> int:
        """Get the index of a given net within the spec's net list."""
        for index, candidate in enumerate(self.nets):
            if candidate.name == n.name:
                return index
        raise KeyError(f"Unknown net {net}")

    def schematic(self, schematic_component: component.Component) -> Optional[str]:
        """Return a schematic reference for a component or None if the component isn't part of a schematic."""

        # If this component is an ancillary with a parent then search for its
        # parent's schematic reference instead
        if schematic_component.ancillary and schematic_component.ancillary.parent:
            schematic_component = schematic_component.ancillary.parent

        for candidate in schematic_component.iterate_ancestors():
            schematic = next(
                (
                    schematic
                    for schematic, ids in self.schematics.items()
                    if candidate.filter_id in ids
                ),
                None,
            )
            if schematic:
                return schematic
        return None

    @property
    def main_board(self) -> component.Component:
        if self.main_board_reference not in self.boards:
            raise KeyError(f"No main board found ({', '.join(self.boards.keys())})!")
        return cast(
            component.Component,
            self.root_component.get_child(self.main_board_reference),
        )

    def is_board(self, component: component.Component) -> bool:
        return component.reference in self.boards

    def board(
        self, board_component: Union[component.ComponentFilter, component.Component]
    ) -> Optional[component.Component]:
        """Return a board for a component or None if the component isn't part of a board."""
        for board in self.board_components():
            for _, child in board.iterate_components():
                if child.filter_id == board_component.filter_id:
                    return board
        return None

    def board_reference(
        self, board_component: Union[component.ComponentFilter, component.Component]
    ) -> Optional[str]:
        """Return a board reference for a component or None if the component isn't part of a board."""
        board = self.board(board_component)
        return board.reference if board else None

    def board_components(self) -> Iterator[component.Component]:
        """Return all components representing boards."""
        for board_reference in self.boards.keys():
            yield cast(
                component.Component, self.root_component.get_child(board_reference)
            )

    def bus_ancillary_components(
        self, bus: bus.Bus, interface_pin: InterfacePin = None,
    ) -> List["component.Component"]:
        """Return all bus-level ancillary components belonging to `component` and `bus`.

        Pass in interface_pin to return only the components that ancillary this interface_pin.
        """

        ancillary_components: List[component.Component] = []

        for candidate in self.root_component.get_atomic_components():
            if not isinstance(candidate, component.Component):
                raise RuntimeError(
                    "bus_ancillary_components called on unresolved component!"
                )

            if (
                not candidate.ancillary
                or candidate.ancillary.applies_to != AncillaryAppliesTo.bus
            ):
                # We're only interested in ancillary components applying to buses
                continue

            if bus != candidate.ancillary.bus:
                # The ancillary's bus must match the request bus
                continue

            if interface_pin and not candidate.ancillary.matches(
                interface_pin_id=interface_pin.id, bus=bus
            ):
                # When filtering by interface pins, only return matching ones.
                continue

            ancillary_components.append(candidate)

        return ancillary_components

    def interface_ancillary_components(
        self,
        parent_component: "component.Component",
        interface: models.Interface = None,
        interface_pin: models.InterfacePin = None,
    ) -> List["component.Component"]:
        """Return all interface-level ancillary components belonging to this component.

        Pass in interface_pin to return only ancillaries that apply to a specific interface_pin.
        Pass in interface to return only ancillaries that apply to a specific interface.
        """

        ancillary_components: List[component.Component] = []

        for candidate in self.root_component.get_atomic_components():
            if not isinstance(candidate, component.Component):
                raise RuntimeError(
                    "interface_ancillary_components called on unresolved component!"
                )
            if (
                not candidate.ancillary
                or candidate.ancillary.applies_to != AncillaryAppliesTo.interface
            ):
                # We're only interested in ancillary components applying to interfaces
                continue

            if (
                candidate.ancillary.parent
                and candidate.ancillary.parent.reference != parent_component.reference
            ):
                # Ancillary has to apply to the right component
                continue

            if interface and candidate.ancillary.interface != interface:
                # Ancillary interface doesn't match requested interface
                continue

            if interface_pin and interface_pin.id not in (
                connection.interface_pin_id
                for connection in candidate.ancillary.connections
            ):
                # Ancillary interface doesn't match requested interface pin
                continue

            ancillary_components.append(candidate)

        return ancillary_components
