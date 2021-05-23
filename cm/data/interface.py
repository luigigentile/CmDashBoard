from dataclasses import dataclass, field
from typing import Any, List, Optional
from uuid import UUID

from cm.db import models
from cm.optimization import types as opt_types

from .interface_group import InterfaceGroup
from .interface_type import InterfaceType
from .pin_assignment import PinAssignment


def _cache_dependencies(db_interface: models.Interface) -> List[Any]:
    pin_assignments = models.PinAssignment.objects.filter(interface=db_interface)
    return [
        db_interface,
        db_interface.interface_type,
        pin_assignments,
        models.Pin.objects.filter(assignments__in=pin_assignments),
    ]


@dataclass(unsafe_hash=True)
class Interface:
    """This class represents the picked interfaces on a Component,
    as opposed to all the possible interfaces on a database component"""

    id: Optional[UUID]  # id of the corresponding models.interface object
    interface_type: InterfaceType
    name: str
    function: str
    is_required: bool
    pin_assignments: List[PinAssignment] = field(hash=False, compare=False, repr=False)
    interface_group: Optional[InterfaceGroup] = field(
        default=None, compare=False, repr=False
    )

    # We sometimes represent interfaces that can take on different types in separated form
    # when that happens, this field points to the "real" interface type.
    # An example for this is an I2C interface, which gets split up into master and slave interfaces.
    parent_interface_type: Optional[InterfaceType] = field(
        default=None, repr=False, compare=False, hash=False
    )

    def from_instance(
        self,
        id: Optional[UUID] = None,
        interface_type: InterfaceType = None,
        name: str = None,
        function: str = None,
        is_required: bool = None,
        pin_assignments: List[PinAssignment] = None,
        interface_group: InterfaceGroup = None,
    ) -> "Interface":
        return Interface(
            id=id or self.id,
            interface_type=interface_type or self.interface_type,
            name=name or self.name,
            function=function or self.function,
            is_required=is_required if is_required is not None else self.is_required,
            pin_assignments=pin_assignments or self.pin_assignments,
            interface_group=interface_group or self.interface_group,
        )

    def to_optimization(self, group: opt_types.Group) -> opt_types.Interface:
        assert (
            self.id
        ), "We currently do not support interfaces without an ID in the optimization"
        # FIXME: to be fixed for hierarchical optimisation"
        optimization_interface = opt_types.Interface(
            group=group,
            id=self.id,
            interface_type=self.interface_type.to_optimization(),
            name=self.name,
            pin_assignments=[],
            interface_group=self.interface_group.to_optimization(group)
            if self.interface_group
            else None,
        )

        # the pin assignments have to be created separate because interface needs to be passed in.
        # This is because we need both objects to reference each other.
        optimization_interface.pin_assignments = [
            pin_assignment.to_optimization(interface=optimization_interface)
            for pin_assignment in self.pin_assignments
        ]

        return optimization_interface

    def __str__(self) -> str:
        pin_assignment_str = ", ".join(
            pin.number
            for pin_assignment in self.pin_assignments
            for pin in pin_assignment.pins
        )
        return f"{self.name} on [{pin_assignment_str}]"

    __repr__ = __str__

    def get_pin_assignment(self, pin_assignment_id: UUID) -> PinAssignment:
        for pin_assignment in self.pin_assignments:
            if pin_assignment.id == pin_assignment_id:
                return pin_assignment
        raise RuntimeError(f"{self} has no pin assignment with id {pin_assignment_id}!")
