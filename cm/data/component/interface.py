from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List, Optional, Set
from uuid import UUID, uuid4

from cm.db import models

if TYPE_CHECKING:
    from cm.data.component import Component


class FilterInterface:
    """This is the shared interface between components and component filters which is used when functionality
    can operate on either of the two.
    """

    filter_id: UUID
    reference: str
    parent: Optional[Component] = None

    @staticmethod
    def generate_id() -> UUID:
        return uuid4()

    @property
    def ancestor_ids(self) -> Set[UUID]:
        ids: Set[UUID] = set()
        if self.parent is not None:
            ids |= self.parent.ancestor_ids
            if self.parent.block is not None:
                ids.add(self.parent.block.id)
        return ids

    def is_in_category(self, category: models.Category) -> bool:
        """Check if a component or filter is part of a specific category, either directly or as a descendant."""
        raise NotImplementedError()

    @staticmethod
    def _local_reference(reference: str) -> str:
        """Static version of local reference, can be used if no instance exists."""
        return reference.rsplit(".", 1)[-1]

    @property
    def local_reference(self) -> str:
        """Return just the local part from a component or filter reference.

        Example:
            U1.IC1.R1 -> R1
        """
        return self._local_reference(self.reference)

    def fetch(self, connectivity_cache: Dict[UUID, models.Connectivity]) -> None:
        """Recursively fetch all feasible children for this component or filter.

        create_bus_requirements_callback is a callback passed into to create the bus fragments for a feasible block.
        This is required because the architecture decides how bus fragments are created, the component can't do it alone
        """
        raise NotImplementedError()

    @property
    def feasible_components(self) -> List[Component]:
        raise NotImplementedError()
