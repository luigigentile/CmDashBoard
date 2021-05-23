from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from cm.db import models
from cm.db.constants import PinType
from cm.optimization import types as opt_types


@dataclass(frozen=True)
class Pin:
    """A pin on a concrete component (part or sub-circuit) in a circuit.

    Analogous to cm.db.models.Pin."""

    id: Optional[UUID]  # id of the corresponding models.Pin object
    pin_type: PinType
    name: str
    number: str
    voltage_reference_pin_id: Optional[UUID] = None
    gnd_reference_pin_id: Optional[UUID] = None

    def __str__(self) -> str:
        return f"{self.pin_type} {self.name} (#{self.number})"

    @classmethod
    def from_db(cls, db_pin: models.Pin) -> "Pin":
        voltage_reference_pin = db_pin.voltage_reference_pin()
        gnd_reference_pin = db_pin.gnd_reference_pin()
        return cls(
            id=db_pin.id,
            pin_type=db_pin.pin_type,
            name=db_pin.name,
            number=db_pin.number,
            voltage_reference_pin_id=voltage_reference_pin.id
            if voltage_reference_pin
            else None,
            gnd_reference_pin_id=gnd_reference_pin.id if gnd_reference_pin else None,
        )

    def to_optimization(self, index: int, group: opt_types.Group) -> opt_types.Pin:
        """Transform this pin into an optimization object.

        Note that index has to be passed in because this index is different from self.number, which can be a string.
        The index is determined using the `pin_order` function."""
        return opt_types.Pin(id=self.id, number=self.number, index=index, group=group)
