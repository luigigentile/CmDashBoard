import bisect
import dataclasses
import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    Iterator,
    List,
    Optional,
    Sequence,
    Set,
    Tuple,
    Union,
    cast,
)
from uuid import UUID

import networkx as nx
from pint.quantity import _Quantity

from cm.data import layout, schemas, serializable
from cm.data.ancillary import Ancillary
from cm.data.bus import Bus
from cm.data.bus_fragment import BusFragment, PinUse
from cm.data.caching import cached
from cm.data.component_interface import ComponentInterface
from cm.data.component_pin import ComponentPin
from cm.data.interface import Interface
from cm.data.interface_group import InterfaceGroup
from cm.data.interface_pin import InterfacePin
from cm.data.interface_specialisation import InterfaceSpecialisation
from cm.data.interface_type import InterfaceType
from cm.data.pin import Pin
from cm.data.pin_assignment import PinAssignment
from cm.data.units import UNITS
from cm.db import models, query
from cm.db.models.pin import pin_order
from cm.db.query.attribute import AttributeQuery
from cm.exceptions import ValidationError
from cm.optimization import types as opt_types

from .filter import ComponentFilter, FilterInterface

Quantity = UNITS.Quantity
INTERFACE_ID = UUID
INTERFACE_PIN_ID = UUID
PIN_ID = UUID

BusCreationCallback = Callable[["ComponentFilter", models.Block], List[BusFragment]]

# Regex defining the format of hierarchical component references.
# These can look like IC1.U1.C1 etc, with everything up the last "." describing the part's hierarchy.
# Only the last part is the reference of a component within the context of its containing component.
REFERENCE_REGEX = r"(?:[^\.]+\.)*(?P<prefix>[A-Z\-\_\$]+)(?P<suffix>\d+)"
ROOT_COMPONENT_REFERENCE = "ROOT1"


def _connectivity_cache_dependencies(connectivity: models.Connectivity) -> List[Any]:
    return [
        connectivity,
        connectivity.pins.all(),
        connectivity.interfaces.all(),
        models.InterfaceType,
        models.InterfacePin,
    ]


def _cache_dependencies(
    block: models.Block = None, connectivity: models.Connectivity = None
) -> List[Any]:
    dependencies = [
        models.InterfaceType,
        models.InterfacePin,
    ]

    if block:
        dependencies += [
            block,
            block.children.all(),
        ]

    if isinstance(block, models.SubCircuit):
        dependencies += [models.InterfaceAdapter]

    if connectivity:
        dependencies += [
            connectivity,
            connectivity.pins.all(),
            connectivity.interfaces.all(),
        ]

    return dependencies


@dataclass(init=False, unsafe_hash=True)
class Component(FilterInterface, serializable.Serializable):
    """A component is a nested representation of anything with a function within a circuit.

    At the lowest level, a component is defined in terms of a single
    **physical electrical component** - which we'll call a `part` here.

    Higher-level components contain other components to create more complex systems of local
    circuitry, whole sub-circuits, or even pre-defined sub-circuits.

    When nesting components, sub-components can be concrete components, or they can be sets
    of possible components filtered via certain attributes. For example, a simple microcontroller
    circuit might specify that it requires an LED and a matching resistor, but leave the specifics
    up to the algorithm to figure out.

    A component can only be defined as a combination of other components, or from a single part.
    In practice this means that either `children` is empty, or part is None.
    """

    SCHEMA = schemas.COMPONENT_SCHEMA
    filter_id: UUID = dataclasses.field(repr=False)  # overwritten from interface class
    component_id: UUID = dataclasses.field(
        repr=False
    )  # overwritten from interface class
    reference: str  # already defined in parent class, but for some reason needs redefining here
    function: str  # what this part does in the circuit - currently just populated from the category slug
    block: Optional[models.Block] = dataclasses.field(repr=False)

    pins: List[ComponentPin] = dataclasses.field(hash=False, repr=False)
    interfaces: List[ComponentInterface] = dataclasses.field(hash=False, repr=False)

    children: Sequence[Union["ComponentFilter", "Component"]] = dataclasses.field(
        hash=False, repr=False
    )

    _external_bus_requirements: List[BusFragment] = dataclasses.field(
        hash=False, repr=False
    )

    # For ancillary components (pull-ups, etc), we store their ancillary on the component itself,
    # to give the component itself the ability to know what it's used for.
    ancillary: Optional[Ancillary] = dataclasses.field(hash=False, repr=False)

    _active_interfaces: Set[Tuple[str, InterfaceType]] = dataclasses.field(
        hash=False, repr=False
    )

    connectivity_id: Optional[UUID] = dataclasses.field(default=None, repr=False)

    def __init__(
        self,
        component_id: UUID,
        filter_id: UUID,
        reference: str,
        function: str,
        block: Optional[models.Block],
        children: Sequence[Union["ComponentFilter", "Component"]],
        interfaces: List[Interface],
        active_pin_uses: Dict[INTERFACE_ID, Dict[INTERFACE_PIN_ID, List[PIN_ID]]],
        external_bus_requirements: List[BusFragment],
        pins: List[Pin],
        parent: "Component" = None,
        ancillary: Ancillary = None,
    ):
        self.component_id = component_id
        self.filter_id = filter_id
        self.reference = reference
        self.function = function
        self.block = block
        self.children = children
        self.parent = parent
        self.ancillary = ancillary

        # Denormalize the connectivity id from block to avoid database access to figure out the connectivity
        if block:
            self.connectivity_id = block.connectivity_id

        # Pins get wrapped in ComponentPin instances so that the pin can be aware of its component
        self.pins = [ComponentPin(component=self, pin=pin) for pin in pins]

        # Interfaces also get wrapped in a helper to compose in the component,
        # but in addition this is where we split interfaces that can act as different types into separate interfaces
        self.interfaces = []
        for interface in interfaces:
            component_interface = ComponentInterface(
                component=self, interface=interface, name=interface.name,
            )
            component_interface.active_pin_uses = {
                interface_pin_id: [
                    PinUse(
                        component_pin=self.get_pin(pin_id),
                        interface_pin=interface.interface_type.pin_dict[
                            interface_pin_id
                        ],
                        interface=component_interface,
                    )
                    for pin_id in pin_ids
                ]
                for interface_pin_id, pin_ids in active_pin_uses.get(
                    interface.id, {}  # type: ignore
                ).items()
            }
            for separated_interface in self.separated_interfaces(component_interface):
                self.interfaces.append(separated_interface)

        self._external_bus_requirements = []
        for bus_fragment in external_bus_requirements:
            self.add_bus_requirement(bus_fragment)

        self._active_interfaces = set()

    @staticmethod
    @cached("connectivity", callback=_connectivity_cache_dependencies)
    def _fetch_connectivity_data(connectivity: models.Connectivity) -> Dict[str, Any]:
        """Helper to fetch all required data that only depends on the connectivity.

        This only exists to allow us to cache data by connectivity, instead of having to fetch it multiple times
        for every component that uses the same connectivity.
        """
        pins = {db_pin.id: Pin.from_db(db_pin) for db_pin in connectivity.pins.all()}

        # Prefetch interface types, which is heavily cached
        interface_types = {
            interface_type.id: interface_type
            for interface_type in InterfaceType.get_all()
        }
        all_interface_pins: Dict[UUID, InterfacePin] = {}
        for interface_type in interface_types.values():
            all_interface_pins.update(interface_type.pin_dict)

        interface_groups = {
            db_parent_interface.id: InterfaceGroup(
                id=db_parent_interface.id,
                name=db_parent_interface.name,
                max_parallel_interfaces=db_parent_interface.max_child_interfaces,
            )
            for db_parent_interface in connectivity.interfaces.filter(
                interface_type__allow_child_interfaces=True
            ).only("id", "name", "max_child_interfaces")
        }

        db_assignment_pins: Dict[UUID, List[Pin]] = defaultdict(list)
        for via in models.PinAssignment.pins.through.objects.filter(
            pin__connectivity=connectivity
        ):
            db_assignment_pins[via.pinassignment_id].append(pins[via.pin_id])

        pin_assignments: Dict[UUID, List[PinAssignment]] = defaultdict(list)
        for db_pin_assignment in models.PinAssignment.objects.filter(
            interface__connectivity=connectivity
        ):
            if parent_pin_id := db_pin_assignment.parent_interface_pin_id:
                parent_pin: Optional[InterfacePin] = all_interface_pins[parent_pin_id]
            else:
                parent_pin = None

            parent_pin_id = db_pin_assignment.parent_interface_pin_id
            pin_assignments[db_pin_assignment.interface_id].append(
                PinAssignment(
                    id=db_pin_assignment.id,
                    interface_pin=all_interface_pins[
                        db_pin_assignment.interface_pin_id
                    ],
                    channel=db_pin_assignment.channel,
                    parent_interface_pin=parent_pin,
                    pins=db_assignment_pins.get(db_pin_assignment.id, []),
                )
            )

        interfaces = [
            Interface(
                id=db_interface.id,
                interface_type=interface_types[db_interface.interface_type_id],
                name=db_interface.name,
                function=db_interface.get_function(),
                is_required=db_interface.is_required,
                pin_assignments=pin_assignments[db_interface.id],
                interface_group=interface_groups[db_interface.parent_id]
                if db_interface.parent_id
                else None,
            )
            for db_interface in connectivity.interfaces.filter(
                interface_type__allow_child_interfaces=False
            )
        ]

        return {
            "pins": list(pins.values()),
            "interface_types": interface_types,
            "interfaces": interfaces,
            "function": connectivity.function,
        }

    @classmethod
    def from_db(
        cls,
        component_id: UUID,
        filter_id: UUID,
        reference: str,
        block: models.Block,
        parent: "Component" = None,
        connectivity: models.Connectivity = None,
        ancillary: Ancillary = None,
        specialisations: List[InterfaceSpecialisation] = None,
    ) -> "Component":
        """Create a new component from a database block object."""
        connectivity = connectivity or block.connectivity

        connectivity_data = cls._fetch_connectivity_data(connectivity)

        # For parts in sub-circuits, we allow pre-definining active pin uses
        if parent and parent.is_subcircuit:
            # The pin uses in the database use block filters, which are connected to the component
            # via references. Those references are local (excluding any references of the parent objects)
            db_reference = Component._local_reference(reference)

            db_pin_uses = models.PinUse.objects.filter(
                subcircuit=parent.block, block_filter__reference=db_reference,
            )
            active_pin_uses: Dict[
                INTERFACE_ID, Dict[INTERFACE_PIN_ID, List[PIN_ID]]
            ] = defaultdict(lambda: defaultdict(list))

            for db_pin_use in db_pin_uses:
                active_pin_uses[db_pin_use.interface_id][
                    db_pin_use.interface_pin_id
                ].append(db_pin_use.pin_id)
        else:
            active_pin_uses = {}

        # If interface specialisations have been specified then replace
        # the specialisable interface with the specialised interfaces
        if specialisations:
            interfaces: List[Interface] = []
            specialisable_interfaces: List[Interface] = []
            for interface in connectivity_data["interfaces"]:
                (
                    specialisable_interfaces
                    if interface.interface_type.can_be_specialised
                    else interfaces
                ).append(interface)

            num_specialisable_interfaces = len(specialisable_interfaces)
            if num_specialisable_interfaces == 0:
                raise RuntimeError(
                    f"{reference} has no interfaces that can be specialised"
                )
            elif num_specialisable_interfaces > 1:
                raise RuntimeError(
                    f"{reference} has more than one interface that can be specialised"
                )

            interfaces.extend(
                [
                    specialisation.to_interface(
                        connectivity.id, specialisable_interfaces[0]
                    )
                    for specialisation in specialisations
                ]
            )

        # Otherwise, just use the interfaces specified by the connectivity
        else:
            interfaces = connectivity_data["interfaces"]

        component = cls(
            component_id=component_id,
            filter_id=filter_id,
            reference=reference,
            function=connectivity_data["function"],
            block=block,
            children=[],
            interfaces=interfaces,
            active_pin_uses=active_pin_uses,
            external_bus_requirements=[],  # These get populated separately
            pins=connectivity_data["pins"],
            parent=parent,
            ancillary=ancillary,
        )

        children = []
        for db_filter in block.children.all():
            child_queryset = query.blocks(
                category=db_filter.category,
                attribute_queries=[
                    AttributeQuery.from_db(query) for query in db_filter.queries.all()
                ],
                connectivity_id=db_filter.connectivity_id,
            )

            children.append(
                ComponentFilter(
                    # Create any sub-filters with nested names. A sub-circuit named X1 with a child R1
                    # will result in a reference called X1.R1
                    category_id=db_filter.category_id,
                    reference=f"{reference}.{db_filter.reference}",
                    reference_label=db_filter.category.get_reference_label(),
                    queryset=child_queryset,
                    parent=component,
                    connectivity_id=db_filter.connectivity_id,
                )
            )
        component.children = children

        return component

    @property
    def external_bus_requirements(self) -> List[BusFragment]:
        return self._external_bus_requirements

    @property
    def external_bus_requirements_dict(self) -> Dict[UUID, BusFragment]:
        return {
            fragment.data_id: fragment for fragment in self.external_bus_requirements
        }

    def _adapt_interface(self, fragment: BusFragment) -> Optional[ComponentInterface]:
        """
        If bus_fragment has an adapter, outputs the new interface that the bus_fragment points to,
        which has been adapted from an original interface.
        Otherwise, it outputs None.
        """

        adapter = fragment.interface_adapter
        if adapter is None:
            return None

        # Check if the component is the "from" or "to" side of this fragment
        is_requesting = fragment.from_filter.reference == self.reference
        # If the targeted interface exists, we can use it directly.

        interface_name = (
            fragment.from_interface_name
            if is_requesting
            else fragment.to_interface_name
        )
        interface_type = (
            fragment.get_from_interface_type()
            if is_requesting
            else fragment.get_to_interface_type()
        )
        original_type = (
            (adapter.original_from_interface_type or fragment.get_from_interface_type())
            if is_requesting
            else (
                adapter.original_to_interface_type or fragment.get_to_interface_type()
            )
        )
        adapted_pins = (
            adapter.adapted_from_pins if is_requesting else adapter.adapted_to_pins
        )
        if not interface_name:
            raise RuntimeError(
                "Got adapted interface that specifies only an interface type, this is not supported."
            )

        # Adapted interfaces are only allowed when specific interfaces are specified,
        # so special care is only needed if an interface is specified
        try:
            self.get_interface(interface_name, interface_type.name)
            return None
        except KeyError:
            # A new interface needs to be created
            original_interface = self.get_interface(interface_name, original_type.name)
            interface = ComponentInterface(
                component=self,
                name=original_interface.name,
                interface=original_interface.interface.from_instance(
                    interface_type=interface_type,
                    pin_assignments=[
                        assignment.from_instance(
                            interface_pin=adapted_pins[assignment.interface_pin]
                        )
                        for assignment in original_interface.interface.pin_assignments
                    ],
                ),
            )
        return interface

    def add_bus_requirement(self, fragment: BusFragment) -> None:
        """Add a bus requirement to the component. Before doing that, this method:
        1. adds an extra interface to the component if mandated by the adapter.
        2. deduce the pin uses, if the bus fragment comes from the database.
        3. activates the from_interface and the to_interface with the deduced pin_uses.

        Here are more details on point 1:
        A user can define bus requirements that aren't natively compatible with the interfaces on a component.
        When that happens, the user has to define an adapter for this interface, which we use here to add a
        manually defined extra interface to the component.
        An example of this is connecting a digital pin to a power pin,
        or possibly in the future more complicated scenarios like bit-banging digital protocols.
        """

        if (adapted_interface := self._adapt_interface(fragment)) is not None:
            self.interfaces.append(adapted_interface)

        # try to deduce from_connections and to_connections
        if (deduction := fragment.deduce_connections(from_component=self)) is not None:

            # the next big tuple unpacking looks ugly
            # but calling activate_interface and updating the pin_uses inside deduce_pin_uses
            # would give too many responsibilities to the mehtod deduce_pin_uses
            from_interface = deduction["from_interface"]
            to_interface = deduction["to_interface"]
            from_connections = deduction["from_connections"]
            to_connections = deduction["to_connections"]
            to_component = to_interface.component

            self.activate_interface(from_interface, from_connections)
            to_component.activate_interface(to_interface, to_connections)

            fragment.from_connections.update(from_connections)
            fragment.to_connections.update(to_connections)

        self._external_bus_requirements.append(fragment)

    def replace_requirement(self, new_requirement: BusFragment) -> None:
        for fragment in self._external_bus_requirements:
            if fragment.data_id == new_requirement.data_id:
                self._external_bus_requirements.remove(fragment)
                break
        else:
            raise KeyError(
                f"Cannot find a bus requirement with data id {new_requirement.data_id}"
            )

        self._external_bus_requirements.append(new_requirement)

    @property
    def interface_groups(self) -> List[InterfaceGroup]:
        return [
            interface.interface_group
            for interface in self.interfaces
            if interface.interface_group
        ]

    def separated_interfaces(
        self, interface: ComponentInterface
    ) -> Iterable[ComponentInterface]:
        """Some interfaces can act as one of several interface types, we need to
        be able to split up these interfaces into separate ones.

        Example:
            an I2C (slave or master) interface turns into one I2C Master and one I2C slave
        """

        child_types = interface.interface_type.children
        if not child_types:
            yield interface

        # This interface needs to be separated, once for each possible type
        for child_type in child_types:

            # Update the pin assignments to use the child type's interface pins corresponding to the original ones.
            child_pin_assignments = []
            child_pin_uses = {}
            for pin_assignment in interface.pin_assignments:
                child_interface_pin = pin_assignment.interface_pin.child_pin_dict[
                    child_type.id
                ]

                if pin_assignment.interface_pin.id in interface.active_pin_uses:
                    child_pin_uses[child_interface_pin.id] = interface.active_pin_uses[
                        pin_assignment.interface_pin.id
                    ]

                child_pin_assignments.append(
                    PinAssignment(
                        id=pin_assignment.id,
                        interface_pin=child_interface_pin,
                        channel=pin_assignment.channel,
                        parent_interface_pin=pin_assignment.parent_interface_pin,
                        original_interface_pin=pin_assignment.interface_pin,
                        pins=pin_assignment.pins,
                    )
                )

            yield ComponentInterface(
                component=self,
                name=interface.name,
                interface=Interface(
                    # Most fields stay the same for all split interfaces
                    id=interface.id,
                    pin_assignments=child_pin_assignments,
                    # the new interface takes the child type
                    interface_type=child_type,
                    name=interface.name,
                    function=interface.function,
                    is_required=interface.is_required,
                    # Remember the original type
                    parent_interface_type=interface.interface_type,
                ),
                active_pin_uses=child_pin_uses,
            )

    @property
    def optimization_group_name(self) -> str:
        # a subcircuit is allocated to its own types.Group shared with no other component
        return (
            (self.f2_group + "/{self.component_id}") if self.children else self.f2_group
        )

    def to_optimization_group(
        self, subcircuit: opt_types.Subcircuit,
    ) -> opt_types.Group:
        if not self.block:
            raise RuntimeError(
                "Tried to run optimization on a component without a block!"
            )

        optimization_filter = subcircuit.get_or_create_filter(self.reference)

        group_name = self.optimization_group_name

        # if the group already exists, do nothing
        if optimization_filter and group_name in optimization_filter.groups_by_name:
            return optimization_filter.groups_by_name[group_name]

        group = opt_types.Group(filter=optimization_filter, name=group_name,)
        optimization_filter.add_group(group)

        ordered_pins = sorted(self.pins, key=lambda p: pin_order(p.pin.number))

        group.pins = [
            component_pin.pin.to_optimization(index, group=group)
            for index, component_pin in enumerate(ordered_pins)
        ]

        # Before turning interfaces into optimisation objects, we need to separate any interfaces
        # that can take on more than one interface type into separate interfaces.
        group.interfaces = [
            component_interface.to_optimization(group)
            for component_interface in self.interfaces
        ]

        group.interface_groups = [
            interface_group.to_optimization(group)
            for interface_group in self.interface_groups
        ]

        group.external_bus_requirements = [
            bus_fragment.to_optimization(group)
            for bus_fragment in self.external_bus_requirements
            if bus_fragment.to_filter.reference
            in subcircuit._filters_by_reference.keys()
            # including only bus_fragments pointing to siblings is enough,
            # because the parent subcircuit was duplicated into a (ghost) sibling
        ]

        return group

    @classmethod
    def root_component(
        cls, children: Sequence[Union["ComponentFilter", "Component"]]
    ) -> "Component":
        root = cls(
            component_id=cls.generate_id(),
            filter_id=cls.generate_id(),
            reference=ROOT_COMPONENT_REFERENCE,
            function="root",
            block=None,
            children=children,
            interfaces=[],
            active_pin_uses={},
            external_bus_requirements=[],
            pins=[],
        )
        for child in children:
            child.parent = root
        return root

    def to_optimization(
        self, subcircuit: opt_types.Subcircuit, create_children: bool = True
    ) -> opt_types.Component:
        """Turn this component into an optimization component."""

        # due to cross-referencing, the optimization objects need to be created in a specific order

        # a group needs to be created before any of its components
        group = self.to_optimization_group(subcircuit)
        optimization_component = opt_types.Component(
            component_id=self.component_id,
            block_id=self.block.id if self.block else None,
            reference=self.reference,
            name=str(self.block.name) if self.block else "",
            group=group,
            size=self.size.to("mm^2").magnitude if self.block and self.is_part else 0,
        )

        # a component needs to be created before its child subcircuit
        if len(self.children) > 0 and create_children:
            optimization_component.subcircuit = self.children_to_optimization(
                parent_component=optimization_component
            )

        return optimization_component

    def children_to_optimization(
        self, parent_component: opt_types.Component = None,
    ) -> opt_types.Subcircuit:

        subcircuit = opt_types.Subcircuit(parent_component=parent_component)

        # these filters would be created in the next for-loop but we have to do it before
        # as feasible_component.to_optimization creates the bus_fragments pointing to sibling filters
        for child in self.children:
            subcircuit.get_or_create_filter(child.reference)
        # create the ghost filter (except for the root component)
        # which is a duplicate of self.to_optimization() into the opt.Subcircuit: this way the bus_fragments from/to
        # parent/child get automaticlally re-routed to all live in the same subcircuit
        if not self.is_root:
            subcircuit.get_or_create_filter(self.reference)

        for child in self.children:
            for feasible_component in child.feasible_components:
                subcircuit.add(feasible_component.to_optimization(subcircuit))
        # add the ghost component to the ghost filter (except for the root component)
        if not self.is_root:
            subcircuit.add(
                self.to_optimization(subcircuit=subcircuit, create_children=False)
            )

        return subcircuit

    def from_optimization(self, optimization_component: opt_types.Component) -> None:
        assert (
            not optimization_component.group.filter.is_ghost_filter
        ), "Ghost component cannot be converted to data component"

        if optimization_component.subcircuit:
            ghost_bus_requirements = [
                filt.groups[0]
                for filt in optimization_component.subcircuit.filters
                if filt.is_ghost_filter
            ][0].external_bus_requirements
        else:
            ghost_bus_requirements = []

        for optimization_bus_fragment in (
            optimization_component.group.external_bus_requirements
            + ghost_bus_requirements
        ):

            # find from_interface and its pin uses
            from_interface = self.get_interface(
                optimization_bus_fragment.from_interface.name,
                optimization_bus_fragment.from_interface.interface_type.name,
            )

            # we need to store the pin_uses in two different data structures:
            # one for the pin_uses of the interface,
            # one for the pin_uses of the bus_fragment
            # note that we include all the pin_uses picked from the piconet and these
            # will replace the already existing pin_uses both on the bus_fragment and the interface
            from_pin_uses: Dict[UUID, List[PinUse]] = defaultdict(
                list
            )  # interface_pin_id -> List[PinUse]
            from_connections: Dict[UUID, List[PinUse]] = defaultdict(
                list
            )  # bus_pin_id -> List[PinUse]

            for (
                optimization_bus_pin,
                optimization_pin_uses,
            ) in optimization_bus_fragment.from_connections.items():
                for optimization_pin_use in optimization_pin_uses:
                    assert optimization_pin_use.pin.id, "Picked pin has no UUID"

                    pin_use = PinUse(
                        component_pin=self.get_pin(optimization_pin_use.pin.id),
                        interface_pin=from_interface.interface_type.pin_dict[
                            optimization_pin_use.interface_pin.id
                        ],
                        interface=from_interface,
                    )

                    from_pin_uses[optimization_pin_use.interface_pin.id].append(pin_use)
                    from_connections[optimization_bus_pin.interface_pin.id].append(
                        pin_use
                    )

            self.activate_interface(from_interface, from_pin_uses)

            # find to_optimization_component (it could be a sibling or the parent)
            if optimization_bus_fragment.to_filter.is_ghost_filter:
                assert (
                    optimization_bus_fragment.to_filter.subcircuit.parent_component
                ), "Ghost filter must have a subcircuit with a parent component"
                # in case it's the parent, the bus_fragment actually points to a ghost_filter
                optimization_to_component = (
                    optimization_bus_fragment.to_filter.subcircuit.parent_component
                )
            else:
                # bus_fragment points to sibling or child
                # (bus_fragment points to a child iff it came from ghost_bus_requirements)
                optimization_to_component = optimization_bus_fragment.to_filter.groups[
                    0
                ].components[0]

            # find to_component
            assert self.parent, "Component that is not root must have a parent"
            to_component = [
                component
                for _, component in self.parent.iterate_components()
                if component.component_id == optimization_to_component.component_id
            ][0]

            # find to_interface and its pin_uses
            assert (
                optimization_bus_fragment.to_interface
            ), "Picked bus fragment has missing to_interface"
            to_interface = to_component.get_interface(
                optimization_bus_fragment.to_interface.name,
                optimization_bus_fragment.to_interface.interface_type.name,
            )

            # as above, we need to store the pin_uses in two different data structures
            to_pin_uses: Dict[UUID, List[PinUse]] = defaultdict(
                list
            )  # interface_pin_id -> List[PinUse]
            to_connections: Dict[UUID, List[PinUse]] = defaultdict(
                list
            )  # bus_pin_id -> List[PinUse]

            for (
                optimization_bus_pin,
                optimization_pin_uses,
            ) in optimization_bus_fragment.to_connections.items():
                for optimization_pin_use in optimization_pin_uses:
                    assert optimization_pin_use.pin.id, "Picked pin has no UUID"

                    pin_use = PinUse(
                        component_pin=to_component.get_pin(optimization_pin_use.pin.id),
                        interface_pin=to_interface.interface_type.pin_dict[
                            optimization_pin_use.interface_pin.id
                        ],
                        interface=to_interface,
                    )

                    to_pin_uses[optimization_pin_use.interface_pin.id].append(pin_use)
                    to_connections[optimization_bus_pin.interface_pin.id].append(
                        pin_use
                    )

            to_component.activate_interface(to_interface, to_pin_uses)

            data_bus_fragment = self.external_bus_requirements_dict[
                optimization_bus_fragment.data_id
            ]

            resolved_bus_fragment = data_bus_fragment.from_instance(
                data_id=data_bus_fragment.data_id,
                from_filter=self,
                to_filter=to_component,
                from_interface_name=from_interface.name,
                to_interface_name=to_interface.name,
                from_interface_type=from_interface.interface_type,
                to_interface_type=to_interface.interface_type,
                from_connections=from_connections,
                to_connections=to_connections,
            )

            self.replace_requirement(resolved_bus_fragment)

    def children_from_optimization(
        self, optimization_subcircuit: opt_types.Subcircuit
    ) -> None:
        self.children = [
            child
            for component_filter in self.children
            for child in component_filter.feasible_components
            if child.component_id
            == optimization_subcircuit._filters_by_reference[component_filter.reference]
            .groups[0]
            .components[0]
            .component_id
        ]  # this automatically excludes ghost components

        for child in self.children:
            assert isinstance(
                child, Component
            ), "Component filter found in solution tree"
            optimization_component = (
                optimization_subcircuit._filters_by_reference[child.reference]
                .groups[0]
                .components[0]
            )

            # all children must be found first so that bus_fragments created in
            # from_optimization can refer to child components in the case the component is a subcircuit
            if len(child.children) > 0:
                assert (
                    optimization_component.subcircuit
                ), "No optimization subcircuit found for component with children"
                child.children_from_optimization(optimization_component.subcircuit)

            # once we get here all the component_filters of the tree have been eliminated:
            # child.is_fully_resolved already equals True
            child.from_optimization(optimization_component)

    def _buses(self, deep: bool = False) -> List[Bus]:
        """Return the list of buses that this component contains.

        If deep is False, then only the buses affecting direct children are returned.
        Otherwise, all descendant buses are considered."""
        interface_graph = nx.Graph()  # A temporary graph where the nodes are interfaces

        descendants_to_consider = (
            [component for _, component in self.iterate_tree()]
            if deep
            else self.children
        )

        for descendant in descendants_to_consider:
            if isinstance(descendant, ComponentFilter):
                raise RuntimeError(
                    "internal_buses called on unresolved component, this makes no sense!"
                )
            for bus_fragment in descendant.external_bus_requirements:
                # Remember which fragment each interface belongs to.
                # Each interface should only ever show up once (otherwise more than one bus would be connected to
                # the same interface)
                if not bus_fragment.from_interface or not bus_fragment.to_interface:
                    raise RuntimeError(
                        "internal_buses called on component with unresolved bus requirements!"
                    )

                interface_graph.add_edge(
                    bus_fragment.from_interface,
                    bus_fragment.to_interface,
                    bus_fragment=bus_fragment,  # networkx allows storing extra data on edges.
                )

        buses = []
        # We use connected components to find the sets of interfaces that are connected (forming a bus).
        for connected_interfaces in nx.connected_components(interface_graph):
            fragments: Set[BusFragment] = set()

            for connected_interface in connected_interfaces:
                connected_fragments = set(
                    edge["bus_fragment"]
                    for edge in interface_graph[connected_interface].values()
                )
                fragments |= connected_fragments

            buses.append(Bus(list(fragments)))

        return buses

    @property
    def internal_buses(self) -> List[Bus]:
        return self._buses(deep=False)

    def flattened_buses(self) -> List[Bus]:
        return self._buses(deep=True)

    def __str__(self) -> str:
        return self.reference

    def display_tree(self, level: int = 1) -> str:
        """Print a prettified version of this component and all its descendants."""
        self_string = f"{self.reference} - {self.block or '(No block)'}"
        if self.ancillary:
            self_string += f" - {self.ancillary.ancillary_type}"
            if self.ancillary.parent and self.ancillary.interface:
                self_string += (
                    f" for {self.ancillary.parent.reference}.{self.ancillary.interface}"
                )
        if not self.children:
            return self_string

        indent = "  " * level
        descendant_string = f"\n{indent}".join(
            child.display_tree(level + 1) for child in self.children
        )
        return f"{self_string}\n{indent}{descendant_string}"

    @property
    def price(self) -> float:
        """Get component price from its block attributes.
        HACK: this should be removed once MOQs are working end-to-end."""

        if not self.block:
            raise RuntimeError("Tried to access price of a component without block!")
        if not self.is_part:
            return 0
        elif "price" not in self.block.attributes:
            return 10000
        else:
            return float(self.block.attributes["price"])

    @property
    def size(self) -> _Quantity:
        """Get component size in mm² from its block attributes.

        Sizes are currently specified only as an area, not as discrete dimensions."""
        if not self.block:
            raise RuntimeError("Tried to get size on a component with no block!")
        size = self.block.attributes.get("size")
        if size is None:
            size = Quantity("10000mm^2")
        return size.to("mm^2")

    @property
    def reference_label(self) -> str:
        """Return the reference label used in the reference of this component.

        Example:
            Component with reference "IC1.R1" has reference label "R"
        """
        m = re.fullmatch(REFERENCE_REGEX, self.reference)
        if not m:
            raise RuntimeError(
                f"Component {self} has invalid reference {self.reference}!"
            )
        return m.group("prefix")

    @staticmethod
    def next_reference_from_list(
        path_prefix: str, prefix: str, existing_references: List[str]
    ) -> str:
        """Calculate the next available reference for a component with reference label "prefix".

        path_prefix is the hierarchical prefix that should be added to the next component.

        Example:
            next_reference_from_list('U1', 'R', existing_references='U1.R1')
            ==> U1.R2

        This static version can be used where a list of components exists without being in a
        component hierarchy.
        """
        existing_numbers: List[int] = []

        for reference in existing_references:
            m = re.fullmatch(REFERENCE_REGEX, reference)
            if not m:
                raise ValidationError(f"Invalid component reference {reference}!")
            if m.group("prefix") == prefix:
                bisect.insort(existing_numbers, int(m.group("suffix")))

        current_reference_number = 1
        for existing_number in existing_numbers:
            if existing_number > current_reference_number:
                return f"{prefix}{current_reference_number}"
            if existing_number < current_reference_number:
                raise RuntimeError(
                    "Logic error in _next_reference, this should never happen!"
                )
            current_reference_number += 1

        return f"{path_prefix}{prefix}{current_reference_number}"

    def next_reference(self, prefix: str) -> str:
        path_prefix = (
            f"{self.reference}." if self.reference != ROOT_COMPONENT_REFERENCE else ""
        )

        return self.next_reference_from_list(
            path_prefix,
            prefix,
            existing_references=[child.reference for child in self.children],
        )

    def next_interface_name(self, interface_type: InterfaceType) -> str:
        """Return the next available interface name for a given interface type."""
        label = interface_type.label
        conflicting_interfaces = [
            interface
            for interface in self.interfaces
            if interface.interface_type.label == label
        ]
        return f"{label}{len(conflicting_interfaces)+1}"

    def flattened_references(self) -> Dict[str, str]:
        """Create a mapping of hierarchical components to flat component references.

        Example:
            for a component with children R1, IC1 (sub-circuit), IC1.IC1 and IC1.R1:

            {
                'R1': 'R1',
                'IC1.IC1': 'IC1',
                'IC1.R1': 'R2',
            }
        """

        used_flattened_references: List[str] = []
        flattened_references = {}

        for candidate_component in self.get_atomic_components():
            # Calculate the flattened component reference that will be used in the export
            flattened_reference = Component.next_reference_from_list(
                path_prefix="",
                prefix=candidate_component.reference_label,
                existing_references=used_flattened_references,
            )
            used_flattened_references.append(flattened_reference)
            flattened_references[candidate_component.reference] = flattened_reference

        return flattened_references

    def prepend_reference(self, prefix: str) -> None:
        """Prepend to this component's reference and to all its children."""
        for _, child in self.iterate_tree(include_root=True):
            child.reference = f"{prefix}.{child.reference}"

    @property
    def f2_group(self) -> str:
        """Form/Function group - All components sharing this group can be interchanged in schematics.

        See https://en.wikipedia.org/wiki/Form,_fit_and_function
        """
        if not self.block:
            raise RuntimeError("Tried to get f2_group on a component with no block!")

        interface_ids = [interface.id for interface in self.interfaces if interface.id]

        # The f2 group consists of all components that have the exact same set of interfaces and bus requirements.
        interface_string = "-".join(
            sorted(str(interface_id) for interface_id in interface_ids)
        )
        interface_hash = hashlib.md5(interface_string.encode("utf-8")).hexdigest()

        required_buses_string = "-".join(
            sorted(
                requirement.reference for requirement in self.external_bus_requirements
            )
        )
        required_buses_hash = hashlib.md5(
            required_buses_string.encode("utf-8")
        ).hexdigest()

        return f"{interface_hash}/{required_buses_hash}"

    @property
    def f3_group(self) -> str:
        """Form/Fit/Function group - like f2 group, but can also be interchanged in layouts.

        See https://en.wikipedia.org/wiki/Form,_fit_and_function
        """
        raise NotImplementedError()

    @property
    def is_part(self) -> bool:
        return self.block is not None and self.block.is_part

    @property
    def is_subcircuit(self) -> bool:
        return self.block is not None and self.block.is_subcircuit

    @property
    def is_root(self) -> bool:
        return self.parent is None

    @property
    def subcircuit(self) -> Optional["Component"]:
        """Return the closest ancestor component that's a sub-circuit."""
        for ancestor in self.iterate_ancestors():
            if ancestor.is_subcircuit:
                return ancestor
        return None

    @property
    def feasible_components(self) -> List["Component"]:
        """When filtering, a component acts as a filter with just itself as a feasible component."""
        return [self]

    @property
    def active_interfaces(self) -> Iterator["ComponentInterface"]:
        for interface in self.interfaces:
            if (interface.name, interface.interface_type) in self._active_interfaces:
                yield interface

    def activate_interface(
        self,
        interface: "ComponentInterface",
        active_pin_uses: Dict[UUID, List[PinUse]],
    ) -> None:
        # this method replaces all the potentially existing active pin_uses of the interface that it is activating
        if not isinstance(interface, ComponentInterface):
            raise TypeError("activate_interface expects a component interface!")

        if interface not in self.interfaces:
            raise RuntimeError(
                f"Cannot activate interface {interface}, it doesn't exist on {self}"
            )
        self._active_interfaces.add((interface.name, interface.interface_type))
        interface.active_pin_uses = active_pin_uses

    def get_assigned_interface_pin(self, pin: ComponentPin) -> Optional[InterfacePin]:
        """Returns the interface pin a given pin is assigned to, if any."""
        for interface in self.interfaces:
            for interface_pin_id, pin_uses in interface.active_pin_uses.items():
                if pin in [pin_use.component_pin for pin_use in pin_uses]:
                    return interface.interface_type.pin_dict[interface_pin_id]
        return None

    def is_in_category(self, category: models.Category) -> bool:
        """Check if a component is within a given category, directly or as a descendant.

        Examples:
            child_category_component.is_in_category(parent_category) -> True
            parent_category_component.is_in_category(child_category) -> False
        """
        if not self.block:
            return False

        return bool(
            self.block.categories.all()
            .get_ancestors(include_self=True)
            .filter(id=category.id)
            .exists()
        )

    def get_footprint_layout(self) -> layout.Layout:
        """Create this part's footprint layout."""
        # FIXME: This shouldn't be hardcoded to kicad footprint files
        from cm.conversion.kicad import kicad_mod_to_layout
        from cm.data.kicad import KiCadMod
        from cm.file_formats.kicad_file_format import KiCadFileFormat

        if not self.block or self.block.is_subcircuit or not self.block.footprint:
            raise RuntimeError(
                "Tried to create a footprint layout for a component that isn't a part!"
            )

        source_file = self.block.footprint.source_file
        kicad_mod = KiCadFileFormat().load(KiCadMod, source_file)
        return kicad_mod_to_layout(cast(KiCadMod, kicad_mod))

    def is_fully_resolved(self) -> bool:
        """Check if a component is fully resolved (contains no unresolved children.)"""
        if self.is_part:
            return True

        for child in self.children:
            if isinstance(child, ComponentFilter):
                return False
            if not child.is_fully_resolved():
                return False

        return True

    def fetch(self, connectivity_cache: Dict[UUID, models.Connectivity]) -> None:
        """Recursively fetch any feasible children for this component.

        Fetching component data is used to separate components from the database. We fetch the
        feasible components once, and then continue processing with that data, so that we don't
        have to worry about the database changing while processing is happening.

        Note that the actual work of fetching information from the database only happens in ComponentFilter.fetch.

        create_bus_requirements_callback (which is passed in by the architecture stage) is called during the
        Component initialization. This is done to give the architecture stage a chance to determine how components
        should be connected to each other.
        """
        for child in self.children:
            child.fetch(connectivity_cache)

        self.add_db_bus_fragments_to_children()

        for child in self.children:
            if not isinstance(child, ComponentFilter):
                continue
            child.add_external_bus_requirements()  # also adds db bus fragments

    def add_db_bus_fragments_to_children(self) -> None:
        """
        If this is a subcircuit, include each of its internal departing bus fragments (pointing to a child)
        """

        if self.children and self.block is not None:
            for db_bus_fragment in self.block.bus_fragments.filter(
                from_filter__isnull=True
            ).select_related("from_interface", "to_interface"):
                try:
                    to_filter = next(
                        child
                        for child in self.children
                        if child.local_reference == db_bus_fragment.to_filter.reference
                    )
                except StopIteration:
                    raise RuntimeError(
                        f"No component '{db_bus_fragment.to_filter}' found for bus fragment to_filter"
                    )

                self.add_bus_requirement(
                    BusFragment.from_db(
                        db_bus_fragment, from_filter=self, to_filter=to_filter
                    ),
                )

    def get_atomic_components(self) -> List["Component"]:
        """Return a list of all atomic (made up of a single part) components used in this component."""
        if self.is_part:
            return [self]

        result: List["Component"] = []
        for child in self.children:
            if not isinstance(child, Component):
                raise RuntimeError(
                    "Tried to retrieve children of an unresolved component."
                )
            result += child.get_atomic_components()
        return result

    def iterate_tree(
        self, include_root: bool = False, parent: "Component" = None
    ) -> Iterator[Tuple[Optional["Component"], Union["Component", "ComponentFilter"]]]:
        if include_root:
            yield parent, self

        for child in self.children:
            if isinstance(child, ComponentFilter):
                yield self, child
            else:
                yield from child.iterate_tree(parent=self, include_root=True)

    def iterate_components(
        self, parent: "Component" = None
    ) -> Iterator[Tuple[Optional["Component"], "Component"]]:
        """Iterates the component tree just like iterate_tree, but returns only components."""
        for parent, component in self.iterate_tree(parent=parent, include_root=True):
            if isinstance(component, Component):
                yield parent, component

    def iterate_filters(
        self, parent: "Component" = None
    ) -> Iterator[Tuple[Optional["Component"], "ComponentFilter"]]:
        """Iterates the component tree just like iterate_tree, but returns only filters."""
        for parent, component in self.iterate_tree(parent=parent, include_root=True):
            if isinstance(component, ComponentFilter):
                yield parent, component

    def iterate_parts(
        self, parent: "Component" = None
    ) -> Iterator[Tuple[Optional["Component"], "Component"]]:
        """Iterates the component tree just like iterate_components, but returns only parts (not sub-circuits)."""
        for parent, component in self.iterate_components(parent=parent):
            if component.is_part:
                yield parent, component

    def iterate_ancestors(self, include_self: bool = True) -> Iterator["Component"]:
        """Iterates "upwards" through this component's ancestors."""
        component: Optional["Component"] = self if include_self else self.parent
        while component:
            yield component
            component = component.parent

    def get_pin_by_name(self, pin_name: str) -> ComponentPin:
        for component_pin in self.pins:
            if component_pin.pin.name == pin_name:
                return component_pin
        raise ValueError(f"Unknown pin {pin_name} on component {self}")

    def get_pin(self, pin_id: UUID) -> ComponentPin:
        for component_pin in self.pins:
            if component_pin.pin.id == pin_id:
                return component_pin
        raise ValueError(f"Unknown pin with id {pin_id} on component {self}")

    def get_child(self, reference: str) -> Union["Component", "ComponentFilter"]:
        for child in self.children:
            if child.reference == reference:
                return child
        raise KeyError(f"Component {self} has no child with reference {reference}!")

    def get_child_by_id(self, filter_id: UUID) -> Union["Component", "ComponentFilter"]:
        for child in self.children:
            if child.filter_id == filter_id:
                return child
        raise KeyError(f"Component {self} has no child with ID {filter_id}!")

    def get_picked_child_by_id(self, component_id: UUID) -> "Component":
        for child in self.children:
            if isinstance(child, ComponentFilter):
                continue
            if child.component_id == component_id:
                return child
        raise KeyError(f"Component {self} has no picked child with ID {component_id}!")

    def has_picked_child_by_id(self, component_id: UUID) -> bool:
        for child in self.children:
            if isinstance(child, ComponentFilter):
                continue
            if child.component_id == component_id:
                return True
        return False

    def has_active_interface(self, interface_name: str) -> bool:
        return any(
            interface.name == interface_name for interface in self.active_interfaces
        )

    def get_active_interface(self, interface_name: str) -> ComponentInterface:
        for interface in self.active_interfaces:
            if interface.name == interface_name:
                return interface

        raise KeyError(f"Active interface with name {interface_name} does not exist!")

    def get_interface(
        self, interface_name: str, interface_type_name: str
    ) -> ComponentInterface:

        candidate_interfaces = [
            interface
            for interface in self.interfaces
            if interface.name == interface_name
            and interface.interface_type.name == interface_type_name
        ]

        if len(candidate_interfaces) == 0:
            raise KeyError(
                f"Found no interfaces with name {interface_name} "
                f"and interface type name {interface_type_name}!"
            )
        if len(candidate_interfaces) > 1:
            raise ValidationError(
                f"Found {len(candidate_interfaces)} interfaces with name {interface_name} "
                f"and interface type name {interface_type_name}!"
            )
        return candidate_interfaces[0]
