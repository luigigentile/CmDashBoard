from dataclasses import dataclass, field
from typing import Dict, Optional

from cm.data.interface_pin import InterfacePin
from cm.data.interface_type import InterfaceType


@dataclass(frozen=True)
class InterfaceAdapter:
    # original->adapted
    adapted_from_pins: Dict[InterfacePin, InterfacePin] = field(hash=False)
    adapted_to_pins: Dict[InterfacePin, InterfacePin] = field(hash=False)

    original_from_interface_type: Optional[InterfaceType]
    adapted_from_interface_type: Optional[InterfaceType]
    original_to_interface_type: Optional[InterfaceType]
    adapted_to_interface_type: Optional[InterfaceType]
