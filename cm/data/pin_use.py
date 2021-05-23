from dataclasses import dataclass
from typing import TYPE_CHECKING

from cm.data.component_pin import ComponentPin
from cm.data.interface_pin import InterfacePin

if TYPE_CHECKING:
    from cm.data.component_interface import ComponentInterface


@dataclass(frozen=True)
class PinUse:
    interface_pin: InterfacePin
    component_pin: ComponentPin
    interface: "ComponentInterface"
