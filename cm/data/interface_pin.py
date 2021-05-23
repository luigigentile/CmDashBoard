from functools import total_ordering
from typing import Any, Dict, List
from uuid import UUID

from cm.data.mixins import ProhibitCopy
from cm.db import models
from cm.db.constants import BusSharing, PinType
from cm.optimization import types as opt_types


# NOTE: this class cannot be a dataclass, as dataclasses seem to have some problems when it comes to
# unpickling objects with circular objects. Normal python classes have no issues with this, but something
# about how dataclasses are managed internally seems to create strange issues.
@total_ordering
class InterfacePin(ProhibitCopy):
    """A pin of an interface type.

    Analogous to cm.db.models.InterfacePin."""

    id: UUID  # id of the corresponding models.InterfacePin object
    interface_type_id: UUID
    reference: str
    pin_type: PinType
    is_required: bool
    sharing: str
    multiple_use: bool

    parent_pins: List["InterfacePin"]
    compatible_pins: List["InterfacePin"]

    # In interface types that can take on multiple concrete roles (like slave/master),
    # this field contains the corresponding child pins the interface pin can be split into.
    # Example: in an i2c (master/slave) interface type, the 'SDA' pin could have two children
    # ('sda (slave)' and 'sda (master'))
    child_pins: List["InterfacePin"]

    def __str__(self) -> str:
        return self.reference

    __repr__ = __str__

    def __init__(
        self,
        id: UUID,
        interface_type_id: UUID,
        reference: str,
        pin_type: PinType,
        is_required: bool,
        sharing: str,
        multiple_use: bool,
        parent_pins: List["InterfacePin"] = None,
        compatible_pins: List["InterfacePin"] = None,
        child_pins: List["InterfacePin"] = None,
    ):
        self.id = id
        self.interface_type_id = interface_type_id
        self.reference = reference
        self.pin_type = pin_type
        self.is_required = is_required
        self.sharing = sharing
        self.multiple_use = multiple_use
        self.parent_pins = parent_pins or []
        self.compatible_pins = compatible_pins or []
        self.child_pins = child_pins or []

    @classmethod
    def _from_db(cls, db_interface_pin: models.InterfacePin) -> "InterfacePin":
        return cls(
            id=db_interface_pin.id,
            interface_type_id=db_interface_pin.interface_type_id,
            reference=db_interface_pin.reference,
            pin_type=db_interface_pin.pin_type,
            is_required=db_interface_pin.is_required,
            sharing=db_interface_pin.sharing,
            multiple_use=db_interface_pin.multiple_use,
            # These have to be populated manually
            parent_pins=[],
            child_pins=[],
            compatible_pins=[],
        )

    def to_optimization(self) -> opt_types.InterfacePin:
        return opt_types.InterfacePin(
            id=self.id,
            reference=self.reference,
            sharable=self.sharing == BusSharing.shared,
            compatible_pin_ids=set(pin.id for pin in self.compatible_pins),
            multiple_use=self.multiple_use,
        )

    @property
    def child_pin_dict(self) -> Dict[UUID, "InterfacePin"]:
        """Return the mapping of child interface types to child interface pins."""
        return {child_pin.interface_type_id: child_pin for child_pin in self.child_pins}

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, InterfacePin):
            return NotImplemented
        return self.id == other.id

    def __lt__(self, other: Any) -> bool:
        if not isinstance(other, InterfacePin):
            return NotImplemented
        return self.id < other.id

    def __hash__(self) -> int:
        return int(self.id)
