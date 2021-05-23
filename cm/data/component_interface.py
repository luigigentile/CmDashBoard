"""Adapter class for putting connectivity-based interfaces onto concrete components."""

import itertools
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Dict, List, Optional, Set
from uuid import UUID

from cm.data.component_pin import ComponentPin
from cm.data.interface import Interface
from cm.data.interface_group import InterfaceGroup
from cm.data.interface_pin import InterfacePin
from cm.data.interface_type import InterfaceType
from cm.data.pin_assignment import PinAssignment
from cm.data.pin_use import PinUse
from cm.optimization import types as opt_types

if TYPE_CHECKING:
    from cm.data.component import Component


@dataclass(unsafe_hash=True)
class ComponentInterface:
    """An interface assigned to a concrete component."""

    component: "Component"
    interface: Interface
    name: str
    active_pin_uses: Dict[UUID, List[PinUse]] = field(
        default_factory=dict, hash=False, compare=False
    )  # interface_pin.id, pin uses

    def __str__(self) -> str:
        pins = [
            pin_use.component_pin.pin.number
            for pin_use in itertools.chain(*self.active_pin_uses.values())
        ]
        return f"{self.name} on {', '.join(pins)}"

    __repr__ = __str__

    def from_instance(
        self,
        component: "Component" = None,
        interface: Interface = None,
        name: str = None,
        active_pin_uses: Dict[UUID, List[PinUse]] = None,
    ) -> "ComponentInterface":
        """Construct a new ComponentInterface from an existing instance."""
        interface = interface or self.interface
        component = component or self.component
        active_pin_uses = (
            active_pin_uses if active_pin_uses is not None else self.active_pin_uses
        )

        # Validate that the pin uses match the given component.
        for pin_uses in active_pin_uses.values():
            for pin_use in pin_uses:
                assert (
                    pin_use.component_pin.component == component
                ), "ComponentInterface got pin uses not matching its component!"

        return ComponentInterface(
            component=component,
            interface=interface,
            active_pin_uses=active_pin_uses,
            name=name or interface.name,
        )

    def to_optimization(self, group: opt_types.Group) -> opt_types.Interface:
        optimization_interface = self.interface.to_optimization(group)

        active_pin_uses = []
        for pin_uses in self.active_pin_uses.values():
            for pin_use in pin_uses:
                active_pin_uses.extend(
                    [
                        optimization_pin_use
                        for optimization_pin_use in optimization_interface.pin_uses
                        if optimization_pin_use.pin
                        == group.pins_by_number[pin_use.component_pin.pin.number]
                        and optimization_pin_use.interface_pin.id
                        == pin_use.interface_pin.id
                    ]
                )
        optimization_interface.active_pin_uses = active_pin_uses

        return optimization_interface

    def active_pins(
        self, interface_pin_id: UUID = None, pin_assignment: PinAssignment = None
    ) -> Set[ComponentPin]:
        """Return a set of all pins active for this interface, optionally filtered by interface pin / assignment."""
        combined_pins: Set[ComponentPin] = set()
        for active_interface_pin_id, active_pin_uses in self.active_pin_uses.items():
            if interface_pin_id and active_interface_pin_id != interface_pin_id:
                # Filter by interface pin, if supplied
                continue

            combined_pins |= set([pin_use.component_pin for pin_use in active_pin_uses])

        # Filter further by pin assignment, if supplied
        if pin_assignment:
            # Get any component pins that match the pin assignment
            assigned_pins = set(
                self.component.get_pin(pin.id) for pin in pin_assignment.pins if pin.id
            )
            # Reduce the active pins down to just the ones that match the assignment
            combined_pins = combined_pins.intersection(assigned_pins)

        return combined_pins

    @property
    def active_interface_pins(self) -> Set[InterfacePin]:
        return {
            self.interface.interface_type.pin_dict[interface_pin_id]
            for interface_pin_id in self.active_pin_uses
        }

    # Proxy attributes to allow accessing interface attributes directly

    @property
    def id(self) -> Optional[UUID]:
        return self.interface.id

    @property
    def interface_type(self) -> InterfaceType:
        return self.interface.interface_type

    @property
    def function(self) -> str:
        return self.interface.function

    @property
    def is_required(self) -> bool:
        return self.interface.is_required

    @property
    def pin_assignments(self) -> List[PinAssignment]:
        return self.interface.pin_assignments

    @property
    def interface_group(self) -> Optional[InterfaceGroup]:
        return self.interface.interface_group
