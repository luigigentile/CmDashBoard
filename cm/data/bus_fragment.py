from collections import defaultdict
from dataclasses import dataclass, field
from typing import (
    TYPE_CHECKING,
    Dict,
    Iterator,
    List,
    Optional,
    Set,
    Tuple,
    TypedDict,
    Union,
    cast,
)
from uuid import UUID, uuid4

from cm.data import schemas
from cm.data.component_interface import ComponentInterface
from cm.data.component_pin import ComponentPin
from cm.data.interface_adapter import InterfaceAdapter
from cm.data.interface_pin import InterfacePin
from cm.data.interface_type import InterfaceType
from cm.data.pin_use import PinUse
from cm.data.serializable import Serializable
from cm.db import models as db_models
from cm.db.constants import BusSharing
from cm.exceptions import ValidationError
from cm.optimization import types as opt_types

if TYPE_CHECKING:
    # Avoid circular import by only importing component filter for type checking, not at runtime.
    from cm.data.component import (  # noqa (needed for type checking)
        Component,
        ComponentFilter,
    )


class ConnectionDeduction(TypedDict):
    from_interface: ComponentInterface
    to_interface: ComponentInterface
    from_connections: Dict[UUID, List[PinUse]]  # interface_pin_id -> List[PinUse]
    to_connections: Dict[UUID, List[PinUse]]  # interface_pin_id -> List[PinUse]


@dataclass(frozen=True, order=True)
class BusFragment(Serializable):
    """A bus fragment between two filters.

    This class is analogous to cm.db.models.BusFragment. It contains the same information, but we
    need a version of bus fragment separate from the database because while some bus fragments are defined
    in the database, some are also created ad-hoc.

    Bus fragments specify a point-to-point connection between two filters or resolved components.

    When referencing components, the bus fragment can also specify a specific interface, but for filters
    only the interface type can be specified.
    """

    SCHEMA = schemas.BUS_FRAGMENT_SCHEMA
    data_id: UUID = field(
        repr=False
    )  # An ID that represents the bus fragment even if it has no db id.

    from_filter: Union["Component", "ComponentFilter"]
    to_filter: Union["Component", "ComponentFilter"]

    function: str

    from_connections: Dict[UUID, List[PinUse]] = field(default_factory=dict, hash=False)
    to_connections: Dict[UUID, List[PinUse]] = field(default_factory=dict, hash=False)

    # the originating db bus fragment object id (if existing - as some BusFragments might not come
    # from the database - e.g architecture stage)
    id: Optional[UUID] = None

    # from_interface_type and to_interface_type are used as filters for which from/to interfaces
    # are allowed for this bus fragment
    # Either one or both of these can be none, in which case the from/to interfaces should already
    # be specified
    # these types all have to be post-adapting
    # if there's an A->D bus fragment in the database, it would here be D->D
    from_interface_type: Optional[InterfaceType] = None
    to_interface_type: Optional[InterfaceType] = None

    # from_interface and to_interface are used when a specific interface should be addressed.
    # Either one or both of these can be none, in which case any matching interface of the appropriate
    # interface type is used.
    from_interface_name: Optional[str] = None
    to_interface_name: Optional[str] = None

    interface_adapter: Optional[InterfaceAdapter] = None

    def __post_init__(self) -> None:
        if not self.from_interface_type and not self.from_interface_name:
            raise ValidationError(
                "At least one of from_interface_type or from_interface_name must be set."
            )

    def __str__(self) -> str:
        from_side = (
            f"{self.from_filter}.{self.from_interface_name}"
            if self.from_interface_name
            else f"{self.from_filter}.{self.from_interface_type}"
        )
        to_side = (
            f"{self.to_filter}.{self.to_interface_name}"
            if self.to_interface_name
            else f"{self.to_filter}.{self.to_interface_type}"
        )
        return f"{from_side} -> {to_side}"

    __repr__ = __str__

    def __iter__(self) -> Iterator[Tuple["Component", Optional[ComponentInterface]]]:
        """Iterate over the from and to component/interface pairs of this bus fragment."""
        yield self.from_component, self.from_interface
        yield self.to_component, self.to_interface

    @classmethod
    def compute_interface_adapter(
        cls,
        db_bus_fragment: db_models.BusFragment,
        original_from_interface_type: InterfaceType,
        original_to_interface_type: InterfaceType,
    ) -> Optional[InterfaceAdapter]:
        # many db adapters turn into just one here, as we're more flexible with the data structures

        interface_types = InterfaceType.get_all_as_dict()
        interface_pins = {
            interface_pin.id: interface_pin
            for interface_type in interface_types.values()
            for interface_pin in interface_type.pins
        }

        db_interface_adapters = db_bus_fragment.interface_adapters.all()

        interface_adapter: Optional[InterfaceAdapter] = None
        if db_interface_adapters:
            adapted_from_pins = {
                interface_pins[db_adapter.original_from_id]: interface_pins[
                    db_adapter.adapted_from_id
                ]
                for db_adapter in db_interface_adapters
                if db_adapter.adapted_from_id
            }
            adapted_to_pins = {
                interface_pins[db_adapter.original_to_id]: interface_pins[
                    db_adapter.adapted_to_id
                ]
                for db_adapter in db_interface_adapters
                if db_adapter.adapted_to_id
            }
            adapted_from_interface_type = (
                interface_types[list(adapted_from_pins.values())[0].interface_type_id]
                if adapted_from_pins
                else original_from_interface_type
            )
            adapted_to_interface_type = (
                interface_types[list(adapted_to_pins.values())[0].interface_type_id]
                if adapted_to_pins
                else original_to_interface_type
            )
            interface_adapter = InterfaceAdapter(
                adapted_from_pins=adapted_from_pins,
                adapted_to_pins=adapted_to_pins,
                original_from_interface_type=original_from_interface_type,
                adapted_from_interface_type=adapted_from_interface_type,
                original_to_interface_type=original_to_interface_type,
                adapted_to_interface_type=adapted_to_interface_type,
            )

        return interface_adapter

    def deduce_connections(
        self, from_component: "Component",
    ) -> Optional[ConnectionDeduction]:
        """
        Here we try to deduce from_connections and to_connections of a bus fragment.
        If we cannot determine a from_interface and a to_interface, we return empty from_connections and to_connections.
        otherwise, we conver the possible cases.
        [case A] from and to interface are compatible: connect the compatible interface pins
        [case B] from and to interfaces are not compatible but of the same type: connect the corresp. interface pins
        [case C] from and to interfaces have exactly one interface pin: assign the input pin to the output pin
        If none of the above cases occurs: raise an error.
        """

        # can only try to deduce if bus_fragment comes from db and it specifies from and to interface types
        if (
            self.id is None
            or self.from_interface_type is None
            or self.to_interface_type is None
        ):
            return None

        to_interface = None
        to_component = None

        # imported here to avoid circular references
        from cm.data.component import Component, ComponentFilter

        # try to make to_filter into a Component
        if isinstance(self.to_filter, Component):
            to_component = self.to_filter
        elif isinstance(self.to_filter, ComponentFilter):
            if (
                self.to_filter._feasible_components
                and len(
                    {
                        component.connectivity_id
                        for component in self.to_filter._feasible_components
                    }
                )
                == 1
            ):  # all feasible components have the same connectivity
                to_component = self.to_filter.feasible_components[0]
        else:
            raise ValueError(
                f"Expected instance of Component or ComponentFilter, got instance of {type(self.to_filter)}!"
            )

        # find from_interface
        from_interface = self.from_interface
        # find to_interface
        if to_component is not None and self.to_interface_name is not None:
            to_interface = to_component.get_interface(
                self.to_interface_name, self.to_interface_type.name
            )  # use this method as the interface could have been adapted

        # only try to deduce pin_uses if from_interface and to_interface are present
        if from_interface is None or to_interface is None:
            return None

        assert to_component is not None  # here for static type checking

        from_connections: Dict[UUID, List[PinUse]] = defaultdict(list)
        to_connections: Dict[UUID, List[PinUse]] = defaultdict(list)

        # case A)
        if self.from_interface_type.is_compatible(self.to_interface_type):
            for pin_assignment in from_interface.interface.pin_assignments:
                from_pin_uses_list = [
                    PinUse(
                        component_pin=[
                            component_pin
                            for component_pin in from_component.pins
                            if component_pin.pin == pin
                        ][0],
                        interface_pin=pin_assignment.interface_pin,
                        interface=from_interface,
                    )
                    for pin in pin_assignment.pins
                ]
                from_connections[pin_assignment.interface_pin.id].extend(
                    from_pin_uses_list
                )
                for to_pin_assignment in to_interface.interface.pin_assignments:
                    # check that the to_interface_pin is compatible with the from_interface_pin
                    if (
                        to_pin_assignment.interface_pin
                        not in pin_assignment.interface_pin.compatible_pins
                    ):
                        continue
                    to_pin_uses_list = [
                        PinUse(
                            component_pin=[
                                component_pin
                                for component_pin in to_component.pins
                                if component_pin.pin == pin
                            ][0],
                            interface_pin=to_pin_assignment.interface_pin,
                            interface=to_interface,
                        )
                        for pin in to_pin_assignment.pins
                    ]
                    to_connections[pin_assignment.interface_pin.id].extend(
                        to_pin_uses_list
                    )

        # case B)
        elif self.from_interface_type == self.to_interface_type:
            for pin_assignment in from_interface.interface.pin_assignments:
                from_pin_uses_list = [
                    PinUse(
                        component_pin=[
                            component_pin
                            for component_pin in from_component.pins
                            if component_pin.pin == pin
                        ][0],
                        interface_pin=pin_assignment.interface_pin,
                        interface=from_interface,
                    )
                    for pin in pin_assignment.pins
                ]
                from_connections[pin_assignment.interface_pin.id].extend(
                    from_pin_uses_list
                )
                # check that the to_interface_pin coincides with the from_interface_pin
                to_pin_assignment = [
                    to_pin_assignment
                    for to_pin_assignment in to_interface.interface.pin_assignments
                    if to_pin_assignment.interface_pin == pin_assignment.interface_pin
                ][0]
                to_pin_uses_list = [
                    PinUse(
                        component_pin=[
                            component_pin
                            for component_pin in to_component.pins
                            if component_pin.pin == pin
                        ][0],
                        interface_pin=to_pin_assignment.interface_pin,
                        interface=to_interface,
                    )
                    for pin in to_pin_assignment.pins
                ]
                to_connections[pin_assignment.interface_pin.id].extend(to_pin_uses_list)

        # case C)
        elif (
            len(from_interface.pin_assignments) == 1
            and len(to_interface.pin_assignments) == 1
            and len(from_interface.pin_assignments[0].pins)
            == len(to_interface.pin_assignments[0].pins)
        ):
            from_pin_uses_list = [
                PinUse(
                    component_pin=[
                        component_pin
                        for component_pin in from_component.pins
                        if component_pin.pin == pin
                    ][0],
                    interface_pin=from_interface.interface_type.pins[0],
                    interface=from_interface,
                )
                for pin_assignment in from_interface.interface.pin_assignments
                for pin in pin_assignment.pins
            ]
            to_connections_list = [
                PinUse(
                    component_pin=[
                        component_pin
                        for component_pin in to_component.pins
                        if component_pin.pin == pin
                    ][0],
                    interface_pin=to_interface.interface_type.pins[0],
                    interface=to_interface,
                )
                for pin_assignment in to_interface.interface.pin_assignments
                for pin in pin_assignment.pins
            ]

            from_connections[
                from_interface.interface_type.pins[0].id
            ] = from_pin_uses_list
            to_connections[
                from_interface.interface_type.pins[0].id
            ] = to_connections_list

        # if cases A), B), C) were not possible, raise an error
        if not (bool(from_connections) or bool(to_connections)):
            raise RuntimeError(
                f"Cannot create connections for bus fragment {self}, "
                "the assigned interfaces are incompatible, they are not of the same type, "
                "and they have more than one interface pin - this is not supported yet."
            )

        # validation: the set of keys of from_connections and to_connections coincide
        if set(from_connections.keys()) != set(to_connections.keys()):
            raise ValidationError(
                f"from_connections and to_connections deduced for {self} have different keys!"
            )

        deduction: ConnectionDeduction = {
            "from_interface": from_interface,
            "to_interface": to_interface,
            "from_connections": from_connections,
            "to_connections": to_connections,
        }
        return deduction

    @classmethod
    def from_db(
        cls,
        db_bus_fragment: db_models.BusFragment,
        from_filter: Union["Component", "ComponentFilter"],
        to_filter: Union["Component", "ComponentFilter"],
    ) -> "BusFragment":
        """Instantiate from database model.
        Currently this only happens for pre-made subcircuits."""

        # find the original interface types (before adaptation)
        interface_types = InterfaceType.get_all_as_dict()
        from_interface_type = interface_types[
            db_bus_fragment.from_interface_type_id
            if db_bus_fragment.from_interface_type_id
            else db_bus_fragment.from_interface.interface_type_id
        ]
        to_interface_type = interface_types[
            db_bus_fragment.to_interface_type_id
            if db_bus_fragment.to_interface_type_id
            else db_bus_fragment.to_interface.interface_type_id
        ]

        interface_adapter = BusFragment.compute_interface_adapter(
            db_bus_fragment, from_interface_type, to_interface_type
        )
        # adapt the interface types if there an adapter was found
        if interface_adapter:
            from_interface_type = (
                interface_adapter.adapted_from_interface_type or from_interface_type
            )
            to_interface_type = (
                interface_adapter.adapted_to_interface_type or to_interface_type
            )

        return cls(
            data_id=db_bus_fragment.id or uuid4(),
            id=db_bus_fragment.id,
            from_filter=from_filter,
            to_filter=to_filter,
            from_interface_name=db_bus_fragment.from_interface.name,
            to_interface_name=db_bus_fragment.to_interface.name,
            from_interface_type=from_interface_type,
            to_interface_type=to_interface_type,
            function=db_bus_fragment.from_interface.get_function(),
            interface_adapter=interface_adapter,
        )

    def from_instance(
        self,
        from_filter: Union["Component", "ComponentFilter"] = None,
        to_filter: Union["Component", "ComponentFilter"] = None,
        from_interface_type: InterfaceType = None,
        to_interface_type: InterfaceType = None,
        function: str = None,
        data_id: Optional[UUID] = None,
        id: Optional[UUID] = None,
        from_interface_name: str = None,
        to_interface_name: str = None,
        interface_adapter: InterfaceAdapter = None,
        to_connections: Optional[Dict[UUID, List[PinUse]]] = None,
        from_connections: Optional[Dict[UUID, List[PinUse]]] = None,
    ) -> "BusFragment":
        """Instantiate from existing object."""

        return BusFragment(
            data_id=data_id or uuid4(),
            from_filter=from_filter or self.from_filter,
            to_filter=to_filter or self.to_filter,
            from_interface_type=from_interface_type or self.from_interface_type,
            to_interface_type=to_interface_type or self.to_interface_type,
            function=function or self.function,
            id=id or self.id,
            from_interface_name=from_interface_name or self.from_interface_name,
            to_interface_name=to_interface_name or self.to_interface_name,
            interface_adapter=interface_adapter or self.interface_adapter,
            from_connections=from_connections or self.from_connections,
            to_connections=to_connections or self.to_connections,
        )

    @property
    def is_resolved(self) -> bool:
        """Represents whether this bus is fully resolved, or is still in a filtering state.

        A bus fragment is resolved if
        - it has a Component as from and to filter, as opposed to a ComponentFilter
        - and has from and to interfaces assigned."""
        from cm.data.component import Component

        return all(
            [
                isinstance(self.from_filter, Component),
                isinstance(self.to_filter, Component),
                self.from_interface_name,
                self.to_interface_name,
            ]
        )

    @property
    def connections(self) -> Dict[ComponentPin, Set[ComponentPin]]:
        """Describes which pins on the "from" side are connected to which pins on the "to" side.
        The format of the data structure is
        {
            from_pin1: {to_pin1, to_pin2, ...},
            from_pin2: {to_pin1, to_pin2, ...}, # note that several keys can have the same exact value
        }
        This information comes directly from self.from_connections and self.to_connections.
        """
        if len(self.from_connections) == 0 or len(self.to_connections) == 0:
            # raise RuntimeError("Tried to access BusFragment connections too early!")
            return {}

        connections: Dict[ComponentPin, Set[ComponentPin]] = defaultdict(set)

        for bus_pin_id, from_pin_use in self.from_connections.items():
            for from_pin in from_pin_use:
                connections[from_pin.component_pin] |= set(
                    pin_use.component_pin for pin_use in self.to_connections[bus_pin_id]
                )

        return connections

    @property
    def reverse_connections(self) -> Dict[ComponentPin, Set[ComponentPin]]:
        """Equivalent to BusFragment.connections, but showing the connections from the perspective of the to-side."""
        reverse_connections: Dict[ComponentPin, Set[ComponentPin]] = defaultdict(set)

        for from_pin, to_pins in self.connections.items():
            for to_pin in to_pins:
                reverse_connections[to_pin].add(from_pin)

        return reverse_connections

    def get_from_interface_type(self) -> InterfaceType:
        """Determine the required type of from_interface.

        from_interface can represent multiple possible interfaces for certain types of interfaces
        (like I2C master and I2C slave making up a single I2C interface)

        On the from side of a bus, only interfaces with can_be_required=True are valid.

        To determine the right one, we check
            - If the interface type is explicitly given as self.from_interface_type
            - If there is only a single possible interface with can_be_required=True

        If those conditions aren't true, this will raise an exception.
        """

        # If the type has been explicitly specified, just return it.
        if self.from_interface_type:
            return self.from_interface_type

        if not self.from_filter.connectivity_id:
            raise RuntimeError(
                "Cannot get from_interface_type on a bus fragment targeting a component filter without a connectivity!"
            )

        if not self.from_interface_name:
            raise RuntimeError(f"Cannot determine from_interface_type of {self}!")

        candidates = [
            interface.interface_type
            for interface in self.from_filter.interfaces
            if interface.name == self.from_interface_name
            and interface.interface_type.can_be_required
        ]

        if not candidates:
            raise KeyError(
                f"BusFragment {self} has no viable from_interface with name {self.from_interface_name}, "
                "cannot determine type!"
            )

        if len(candidates) > 1:
            raise RuntimeError(
                f"BusFragment {self} matches multiple possible from_interfaces, this is not allowed! "
                f"Interface candidates are {candidates}. You may need to specify from_interface_type."
            )

        return candidates[0]

    def get_to_interface_type(self) -> InterfaceType:
        """Determine the required type of to_interface.

        to_interface can represent multiple possible interfaces for certain types of interfaces
        (like I2C master and I2C slave making up a single I2C interface)

        To determine the right one, we check
            - If the interface type is explicitly given as self.to_interface_type
            - If there is only a single possible interface compatible with self.from_interface_type (if given)
            - If neither of those checks result in a single type, we require that there's only a single possible one.

        If those conditions aren't true, this will raise an exception.
        """

        # If the type has been explicitly specified, just return it.
        if self.to_interface_type:
            return self.to_interface_type

        if not self.to_filter.connectivity_id:
            raise RuntimeError(
                "Cannot get to_interface_type on a bus fragment targeting a component filter without a connectivity!"
            )

        if not self.to_interface_name:
            raise RuntimeError(f"Cannot determine to_interface_type of {self}!")

        candidates = [
            interface.interface_type
            for interface in self.to_filter.interfaces
            if interface.name == self.to_interface_name
        ]

        # If there's only a single candidate, return it
        # FIXME: the logic is here is wrong, we're explicitly returning the candidate without checking its
        # compatibility. We currently have to do this because we cannot distinguish between bus fragments that act
        # as proxies (using the same type on both sides regardless of compatibility) and "real" bus fragments.
        if len(candidates) == 1:
            return candidates[0]

        # If self.from_interface_type is given, we can filter the candidates down further by their connectivity
        from_interface_type = self.get_from_interface_type()
        if from_interface_type:
            candidates = [
                candidate
                for candidate in candidates
                if candidate in from_interface_type.compatible_interface_types
            ]

        if not candidates:
            raise KeyError(
                f"BusFragment {self} has no viable to_interface with name {self.to_interface_name}, "
                "cannot determine type!"
            )

        if len(candidates) > 1:
            raise RuntimeError(
                f"BusFragment {self} matches multiple possible to_interfaces, this is not allowed! "
                f"Interface candidates are {candidates}. You may need to specify to_interface_type."
            )

        return candidates[0]

    @property
    def from_interface(self) -> Optional[ComponentInterface]:
        from cm.data.component import Component

        if not isinstance(self.from_filter, Component):
            raise RuntimeError(
                "Cannot get from_interface on a bus fragment targeting a component filter!"
            )

        interface_type = self.get_from_interface_type()
        if not self.from_interface_name or not interface_type:
            return None

        return self.from_filter.get_interface(
            self.from_interface_name, interface_type.name
        )

    @property
    def from_interface_pins(self) -> Set[InterfacePin]:
        """Get the "from" interface pins for this fragment."""

        if not self.is_resolved:
            raise RuntimeError(
                "Called from_interface_pins on an unresolved bus fragment!"
            )

        return cast(ComponentInterface, self.from_interface).active_interface_pins

    @property
    def to_interface_pins(self) -> Set[InterfacePin]:
        """Get the "to" interface pins for this fragment."""

        if not self.is_resolved:
            raise RuntimeError(
                "Called to_interface_pins on an unresolved bus fragment!"
            )

        return cast(ComponentInterface, self.to_interface).active_interface_pins

    @property
    def to_interface(self) -> Optional[ComponentInterface]:
        from cm.data.component import Component

        if not isinstance(self.to_filter, Component):
            raise RuntimeError(
                "to_interface called on a bus targeting a component filter!"
            )

        interface_type = self.get_to_interface_type()
        if not self.to_interface_name or not interface_type:
            return None

        return self.to_filter.get_interface(self.to_interface_name, interface_type.name)

    @property
    def from_component(self) -> "Component":
        from cm.data.component import Component

        if not isinstance(self.from_filter, Component):
            raise RuntimeError("from_component called on an unresolved component!")
        return self.from_filter

    @property
    def to_component(self) -> "Component":
        from cm.data.component import Component

        if not isinstance(self.to_filter, Component):
            raise RuntimeError("to_component called on an unresolved component!")
        return self.to_filter

    @property
    def reference(self) -> str:
        """Return a reference for this bus, which identifies which buses may be joined together for the schematic.

        In general, any buses with a shareable interface type that share the same interface family have the same
        reference.
        """

        if not self.from_interface:
            raise RuntimeError(
                "Can't get a reference for a bus without a from_interface!"
            )

        family_label = (
            self.from_interface.interface_type.family.label
            if self.from_interface.interface_type.family.id
            else self.from_interface.interface_type.label
        )
        local_reference = f"{family_label}__{self.function}"

        if any(
            pin.sharing == BusSharing.shared
            for pin in self.from_interface.interface_type.pins
        ):
            return local_reference

        # For non-shared buses, we need to make the bus reference global by adding the from filter's reference
        global_reference = f"{self.from_filter.reference}__{local_reference}"

        if self.from_interface_name:
            global_reference += f"__{self.from_interface_name}"
        else:
            raise RuntimeError(
                "Bus fragments with no specified from_interface are not supported yet!"
            )

        return global_reference

    @property
    def interface_set(self) -> Set[ComponentInterface]:
        """Returns the set of the interfaces this fragment contains."""
        interfaces = set()
        if self.from_interface:
            interfaces.add(self.from_interface)
        if self.to_interface:
            interfaces.add(self.to_interface)
        return interfaces

    @classmethod
    def _pin_uses_coincide(
        cls, pin_use: PinUse, optimization_pin_use: opt_types.PinUse
    ) -> bool:
        """
        Helper function that establishes whether a data.PinUse and an optimization PinUse correspond to each other.
        """

        return (
            pin_use.component_pin.pin.number == optimization_pin_use.pin.number
            and pin_use.interface_pin.id == optimization_pin_use.interface_pin.id
        )

    def connections_to_optimization(
        self,
        from_interface: Optional[opt_types.Interface],
        to_interface: Optional[opt_types.Interface],
    ) -> Tuple[
        Dict[opt_types.BusPin, List[opt_types.PinUse]],
        Dict[opt_types.BusPin, List[opt_types.PinUse]],
    ]:
        """
        Given the bus fragment from_connections and to_connections,
        construct the corresponding optimization from_connections and to_connections.
        """

        from_connections: Dict[opt_types.BusPin, List[opt_types.PinUse]] = defaultdict(
            list
        )
        to_connections: Dict[opt_types.BusPin, List[opt_types.PinUse]] = defaultdict(
            list
        )

        if from_interface is None or to_interface is None:
            return from_connections, to_connections

        for index, interface_pin_id in enumerate(self.from_connections.keys()):
            optimization_interface_pins = [
                optimization_interface_pin
                for optimization_interface_pin in from_interface.interface_pins
                if optimization_interface_pin.id == interface_pin_id
            ]
            # using from_interface or to_interface makes no difference here
            if len(optimization_interface_pins) != 1:
                raise ValidationError(
                    f"Expecting exactly one interface pin with id {interface_pin_id} "
                    f"for optimization interface {from_interface}, found {len(optimization_interface_pins)}!"
                )
            optimization_interface_pin = optimization_interface_pins[0]

            optimization_bus_pin = opt_types.BusPin(
                interface_pin=optimization_interface_pin, index=index
            )

            from_connections[optimization_bus_pin] = [
                optimization_pin_use
                for optimization_pin_use in from_interface.pin_uses
                for pin_use in self.from_connections[interface_pin_id]
                if BusFragment._pin_uses_coincide(pin_use, optimization_pin_use)
            ]
            to_connections[optimization_bus_pin] = [
                optimization_pin_use
                for optimization_pin_use in to_interface.pin_uses
                for pin_use in self.to_connections[interface_pin_id]
                if BusFragment._pin_uses_coincide(pin_use, optimization_pin_use)
            ]

            # validation: the set of keys of from_connections and to_connections coincide (for the optimization)
            if set(from_connections.keys()) != set(to_connections.keys()):
                raise ValidationError(
                    f"{[bus_pin.interface_pin.reference for bus_pin in from_connections.keys()]} != "
                    f"{[bus_pin.interface_pin.reference for bus_pin in to_connections.keys()]}"
                )

        return from_connections, to_connections

    def get_optimization_interfaces(
        self, group: opt_types.Group, to_filter: opt_types.Filter
    ) -> Tuple[opt_types.Interface, Optional[opt_types.Interface]]:
        """
        Find the from_interface and to_interface optimization objects corresponding to
        self.from_interface and self.to_interface.
        """

        from_interface = group.get_interface(
            self.from_interface_name,
            self.from_interface_type.name if self.from_interface_type else None,
        )

        # If this bus targets a specific connectivity, we can find the optimization to_interface
        to_interface: Optional[opt_types.Interface] = None
        if self.to_interface_name:
            if not self.to_filter.connectivity_id:
                raise RuntimeError(
                    "Tried to get to_interface_type of bus fragment targetting a filter without a connectivity! "
                    f"Please specifify a connectivity for {self.to_filter}."
                )

            from cm.data.component import Component

            if isinstance(self.to_filter, Component):
                to_component = self.to_filter
            else:
                # If the to filter is a filter, rather than a concrete component, just use the first
                # part. This is assuming that this scenario only happens for filters that address one specific
                # connectivity, and result in a single optimisation group.
                to_component = self.to_filter.feasible_components[0]
                assert to_component.connectivity_id == self.to_filter.connectivity_id

            to_group = to_component.to_optimization_group(
                to_filter.subcircuit
            )  # to_group might not exist yet

            to_interface = to_group.get_interface(
                self.to_interface_name,
                self.to_interface_type.name if self.to_interface_type else None,
            )

        return from_interface, to_interface

    def to_optimization(self, group: opt_types.Group,) -> opt_types.GroupBusFragment:

        subcircuit = group.filter.subcircuit
        from_filter = subcircuit.get_or_create_filter(self.from_filter.reference)
        to_filter = subcircuit.get_or_create_filter(self.to_filter.reference)

        assert from_filter == group.filter, RuntimeError(
            f"Bus fragment {self} does not depart from the filter {group.filter} of its group {group}, "
            f"but rather from filter {from_filter}!"
        )

        from_interface, to_interface = self.get_optimization_interfaces(
            group, to_filter
        )

        # construct from_connections and to_connections for the optimization bus fragment
        from_connections, to_connections = self.connections_to_optimization(
            from_interface, to_interface
        )

        from_interface_type = (
            self.from_interface_type.to_optimization()
            if self.from_interface_type
            else from_interface.interface_type
        )

        return opt_types.GroupBusFragment(
            data_id=self.data_id,
            id=self.id,
            from_filter=from_filter,
            from_group=group,
            to_filter=to_filter,
            from_interface=from_interface,
            to_interface=to_interface,
            from_interface_type=from_interface_type,
            from_connections=from_connections,
            to_connections=to_connections,
        )
