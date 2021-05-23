import dataclasses
from dataclasses import dataclass
from typing import Dict, List
from uuid import UUID, uuid4

from cm.db.models.pin import pin_order

from .interface import Interface
from .interface_pin import InterfacePin
from .interface_type import InterfaceType
from .pin_assignment import PinAssignment


@dataclass
class InterfaceSpecialisation:
    interface_type: InterfaceType
    name: str
    pin_assignments: Dict[InterfacePin, List[int]]

    _cache: Dict[UUID, Interface] = dataclasses.field(default_factory=dict)

    def to_interface(
        self, connectivity_id: UUID, specialisable_interface: Interface,
    ) -> Interface:

        # Specialisations must be cached by connectivity as the pick and connect
        # relies on interfaces in the same group having the same ID
        if connectivity_id not in self._cache:
            specialisable_pins = sorted(
                (
                    pin
                    for pin_assignment in specialisable_interface.pin_assignments
                    for pin in pin_assignment.pins
                ),
                key=lambda pin: pin_order(pin.number),
            )

            pin_assignments = []
            for interface_pin, pin_indices in self.pin_assignments.items():
                if len(specialisable_pins) < max(pin_indices):
                    raise RuntimeError(
                        f"Got specialised pin index out of range for {interface_pin}"
                    )
                pin_assignments.append(
                    PinAssignment(
                        id=None,
                        interface_pin=interface_pin,
                        channel=0,
                        parent_interface_pin=None,
                        pins=[
                            specialisable_pins[pin_index - 1]
                            for pin_index in pin_indices
                        ],
                    )
                )

            self._cache[connectivity_id] = Interface(
                id=uuid4(),
                interface_type=self.interface_type,
                name=self.name,
                function=self.interface_type.function,
                # TODO: Currently specialised interfaces just inherit their is_required
                # value from their interface type's can_be_required. In the future it should
                # be possible for users to specify this.
                is_required=self.interface_type.can_be_required,
                pin_assignments=pin_assignments,
            )

        return self._cache[connectivity_id]
