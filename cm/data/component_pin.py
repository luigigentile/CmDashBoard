"""Adapter classes for putting connectivity-based objects onto components."""


from dataclasses import dataclass
from typing import TYPE_CHECKING

from cm.data.pin import Pin

if TYPE_CHECKING:
    from cm.data.component import Component


@dataclass(frozen=True)
class ComponentPin:
    """A pin assigned to a concrete component."""

    component: "Component"
    pin: Pin

    def __str__(self) -> str:
        return f"{self.pin}"

    __repr__ = __str__
