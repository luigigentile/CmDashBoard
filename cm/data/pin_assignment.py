from dataclasses import dataclass, field
from typing import List, Optional
from uuid import UUID

from cm.data.interface_pin import InterfacePin
from cm.data.pin import Pin
from cm.optimization import types as opt_types


@dataclass(frozen=True, eq=False)
class PinAssignment:
    """A pin assignment on a concrete component (part or sub-circuit) in a circuit.

    Every pin assignment results in one pin being picked.
        - A single pin assignment with multiple pins means "assign this interface pin to one of these pins"
        - Multipe pin assignments with the same interface pin mean "pick multiple pins for this interface pin."

    Analogous to cm.db.models.Pin.Assignment"""

    id: Optional[UUID]  # id of the corresponding models.PinAssignment object
    interface_pin: InterfacePin
    channel: int

    # An optional pin on an interface group, used for restricting pin assignments further. (see model for details)
    parent_interface_pin: Optional[InterfacePin] = field(
        hash=False, compare=False, repr=False
    )
    pins: List[Pin] = field(hash=False, compare=False, repr=False)

    # Sometimes we separate interfaces into multiple interfaces for p&c,
    # like i2c turning into i2c-master and i2c-slave. In cases like that, this field points
    # to the interface pin on the original interface.
    original_interface_pin: Optional[InterfacePin] = None

    def __str__(self) -> str:
        return f"{self.interface_pin} on {self.pins}"

    def from_instance(
        self,
        id: UUID = None,
        interface_pin: InterfacePin = None,
        channel: int = None,
        parent_interface_pin: Optional[InterfacePin] = None,
        pins: List[Pin] = None,
        original_interface_pin: InterfacePin = None,
    ) -> "PinAssignment":
        return PinAssignment(
            id=id or self.id,
            interface_pin=interface_pin or self.interface_pin,
            channel=channel or self.channel,
            parent_interface_pin=self.parent_interface_pin,
            pins=pins or self.pins,
            original_interface_pin=original_interface_pin
            or self.original_interface_pin,
        )

    def to_optimization(
        self, interface: opt_types.Interface
    ) -> opt_types.PinAssignment:
        """Transform this pin into an optimization object.

        Note that interface has to be passed in, because both objects reference each other.
        Recreating it here would cause an infinite loop.
        """
        return opt_types.PinAssignment(
            id=self.id,
            pins=[interface.group.pins_by_number[pin.number] for pin in self.pins],
            interface=interface,
            interface_pin=self.interface_pin.to_optimization(),
        )
