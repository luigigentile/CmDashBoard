from dataclasses import dataclass
from typing import Any, List, Optional
from uuid import UUID

from cm.db import models
from cm.optimization import types as opt_types


def _cache_dependencies(db_interface: models.Interface) -> List[Any]:
    pin_assignments = models.PinAssignment.objects.filter(interface=db_interface)
    return [
        db_interface,
        db_interface.interface_type,
        pin_assignments,
        models.Pin.objects.filter(assignments__in=pin_assignments),
    ]


@dataclass(frozen=True)
class InterfaceGroup:
    """An interface group (modelled as a parent interface in the db) of a component."""

    id: Optional[UUID]  # id of the corresponding parent interface object
    name: str
    max_parallel_interfaces: int

    def __str__(self) -> str:
        return self.name

    @classmethod
    def from_db(cls, db_interface: models.Interface) -> "InterfaceGroup":
        return cls(
            id=db_interface.id,
            name=db_interface.name,
            max_parallel_interfaces=db_interface.max_child_interfaces,
        )

    def to_optimization(self, group: opt_types.Group) -> opt_types.InterfaceGroup:
        return opt_types.InterfaceGroup(
            name=self.name,
            max_parallel_interfaces=self.max_parallel_interfaces,
            group=group,
        )
