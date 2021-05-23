from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Dict, Iterator, List, Optional, Set, Tuple, Union
from uuid import UUID, uuid4

from django.db.models import Count, Prefetch, Q, QuerySet

from cm.data import schemas, serializable
from cm.data.bus_fragment import BusFragment
from cm.data.interface import Interface
from cm.data.interface_specialisation import InterfaceSpecialisation
from cm.data.interface_type import InterfaceType
from cm.db import models

from .interface import FilterInterface

if TYPE_CHECKING:
    from cm.data.component import Component


@dataclass(unsafe_hash=True)
class ComponentFilter(FilterInterface, serializable.Serializable):
    """The ComponentFilter class is used when a component has multiple options for which
    component to use as a child. The filters allow specifying what a child component needs
    to be selected as a child of another component.

    As an example, a microcontroller circuit might have a component filter that specifies a
    power supply with 5V output and at least 1A - it doesn't matter which exact supply is chosen.
    """

    SCHEMA = schemas.COMPONENT_FILTER_SCHEMA
    queryset: QuerySet
    category_id: UUID
    reference: str  # already defined in parent class, but for some reason needs redefining here
    reference_label: str
    links: Set[UUID] = field(
        init=False, hash=False, default_factory=set
    )  # User specified "connections" between sibling component filters
    connectivity_id: Optional[
        UUID
    ]  # If this filter targets a specific connectivity, this is populated.
    specialisations: List[InterfaceSpecialisation] = field(
        init=False, hash=False, default_factory=list
    )

    _feasible_components: Optional[List["Component"]] = field(
        init=False, hash=False, default=None
    )
    _feasible_blocks: Optional[List["models.Block"]] = field(
        init=False, hash=False, default=None
    )

    def __init__(
        self,
        reference: str,
        reference_label: str,
        queryset: QuerySet,
        category_id: UUID,
        filter_id: Optional[UUID] = None,
        connectivity_id: Optional[UUID] = None,
        parent: "Component" = None,
        links: Optional[Set[UUID]] = None,
        specialisations: List[InterfaceSpecialisation] = None,
    ):
        self.filter_id = filter_id or self.generate_id()
        self.reference = reference
        self.reference_label = reference
        self.queryset = queryset
        self.category_id = category_id
        self.parent = parent
        self.connectivity_id = connectivity_id
        self.specialisations = specialisations or []
        self.links = links or set()

    def __str__(self) -> str:
        return f"{self.reference}"

    def display_tree(self, level: int = 1) -> str:
        """Print a prettified version of this filter used for displaying the component tree."""
        return f"Filter {self.reference}"

    def is_in_category(self, category: models.Category) -> bool:
        """Check if a filter is within a given category, directly or as a descendant.

        Examples:
            child_category_filter.is_in_category(parent_category) -> True
            parent_category_filter.is_in_category(child_category) -> False
        """

        return bool(
            category.get_descendants(include_self=True)
            .filter(id=self.category_id)
            .exists()
        )

    @property
    def feasible_blocks(self) -> QuerySet:
        if self._feasible_blocks is None:
            feasible_blocks_qs = (
                self.queryset.exclude(id__in=self.ancestor_ids)
                .distinct()
                .prefetch_related(
                    Prefetch(
                        "manufacturer_parts",
                        queryset=models.ManufacturerPart.objects.select_related(
                            "manufacturer"
                        ),
                    )
                )
            )

            # Filter out components that don't have an interface that can be specialised
            # with enough pins to satisfy our specialisations
            # FIXME: This assumes that components won't have interfaces that can
            # be specialised that are blocked by other interfaces
            if self.specialisations:
                feasible_blocks_qs = feasible_blocks_qs.annotate(
                    specialisable_pins=Count(
                        "connectivity__interfaces__pin_assignments",
                        filter=Q(
                            connectivity__interfaces__interface_type__can_be_specialised=True
                        ),
                    )
                ).filter(
                    specialisable_pins__gte=sum(
                        sum(
                            len(pins)
                            for pins in specialisation.pin_assignments.values()
                        )
                        for specialisation in self.specialisations
                    )
                )

            self._feasible_blocks = feasible_blocks_qs

        return self._feasible_blocks

    def fetch_subcircuit_bus_requirements(
        self,
    ) -> List[Tuple[models.BusFragment, Union["Component", "ComponentFilter"]]]:
        # If this filter has a parent, get any fixed external bus requirements
        #
        # This is required when this ComponentFilter is a child of a sub-circuit
        # as it will have its bus requirements defined by the sub-circuit.
        # We only store the db_bus_fragment and fetch the bus fragment later for each feasible component
        fixed_bus_requirements: List[
            Tuple[models.BusFragment, Union["Component", "ComponentFilter"]]
        ] = []
        if self.parent is not None and self.parent.block is not None:
            for db_bus_fragment in self.parent.block.bus_fragments.filter(
                from_filter__reference=self.local_reference
            ).select_related("from_interface", "to_interface"):
                # If to_filter is null, connect _to_ the parent sub-circuit
                if not db_bus_fragment.to_filter:
                    to_filter: Union[Component, ComponentFilter] = self.parent

                # Otherwise, connect _to_ one of our sibling components
                else:
                    try:
                        to_filter = next(
                            component
                            for component in self.parent.children
                            if component.local_reference
                            == db_bus_fragment.to_filter.reference
                        )
                    except StopIteration:
                        raise RuntimeError(
                            f"No component '{db_bus_fragment.to_filter}' found for bus fragment to_filter"
                        )

                fixed_bus_requirements.append((db_bus_fragment, to_filter))
        return fixed_bus_requirements

    def fetch_architecture_bus_requirements(
        self,
        component: "Component",
        bus_requirements_cache: Dict[str, List[BusFragment]],
    ) -> Iterator[BusFragment]:
        assert component.block, "Feasible component without a block"

        # For each of this filter's links return a bus fragment _from_ the component _to_ the filter
        for to_filter_id in self.links:
            cache_key = f"{component.block.connectivity_id}-{to_filter_id}"

            # Get/create external bus requirements from this component reference/connectivity to the to_filter
            if cache_key not in bus_requirements_cache:
                bus_requirements_cache[cache_key] = []

                # Get to_filter from ID
                if not self.parent:
                    raise RuntimeError(
                        f"Unable to create bus requirements for component filter '{self.reference}' without parent"
                    )

                to_filter = next(
                    (
                        child
                        for child in self.parent.children
                        if child.filter_id == to_filter_id
                    ),
                    None,
                )
                if not to_filter:
                    raise RuntimeError(
                        f"Unknown filter_id '{to_filter_id}' in links for '{self.reference}'"
                    )

                # Get any interfaces that have a bus_fragment. For now, that just means that the interface
                # type is marked as "can be required", which communicates that it's a peripheral / slave
                # interface / interface with a specific function.
                # For more complex architectures, we will need to look at the connection rules and interface
                # functions.
                for interface in component.interfaces:
                    if not interface.is_required:
                        continue
                    bus_requirements_cache[cache_key].append(
                        BusFragment(
                            data_id=uuid4(),
                            from_filter=component,
                            to_filter=to_filter,
                            from_interface_name=interface.name,
                            from_interface_type=interface.interface_type,
                            function=interface.function,
                        )
                    )

            # Return external bus requirements for this to_filter
            yield from bus_requirements_cache[cache_key]

    def add_external_bus_requirements(self) -> None:
        # FIXME: This cache is currently necessary as the optimisation groups all bus fragments
        # by connectivity. If we don't have the same bus fragment used for all components in a
        # group then when re-constructing in from_optimisation the bus fragment won't be found
        # in external_bus_requirements_dict.
        bus_requirements_cache: Dict[str, List[BusFragment]] = {}

        for component in self.feasible_components:
            if component.block is None:
                raise RuntimeError(
                    f"Can't add external bus requirements for component '{component.reference}' without block"
                )

            # Add any db bus fragments between this component and its siblings / parent
            # which are stored on the db parent subcircuit
            for db_bus_fragment, to_filter in self.fetch_subcircuit_bus_requirements():
                component.add_bus_requirement(
                    BusFragment.from_db(
                        db_bus_fragment, from_filter=component, to_filter=to_filter,
                    )
                )

            # Add any bus fragments defined by the filter's links
            for bus_fragment in self.fetch_architecture_bus_requirements(
                component, bus_requirements_cache
            ):
                component.add_bus_requirement(bus_fragment)

    def fetch(self, connectivity_cache: Dict[UUID, models.Connectivity]) -> None:
        """Recursively fetch all feasible components for this filter."""
        from cm.data.component import Component

        if not self.feasible_blocks:
            raise RuntimeError(f"No feasible components for {self}")

        feasible_components = []
        for block in self.feasible_blocks:
            if block.connectivity_id not in connectivity_cache:
                connectivity_cache[block.connectivity_id] = block.connectivity

            # Create a feasible component for this filter
            component = Component.from_db(
                component_id=Component.generate_id(),
                filter_id=self.filter_id,
                reference=self.reference,
                block=block,
                connectivity=connectivity_cache[block.connectivity_id],
                parent=self.parent,
                specialisations=self.specialisations,
            )

            # Fetch feasible components for any children of the component
            component.fetch(connectivity_cache)
            feasible_components.append(component)

        self._feasible_components = feasible_components

    @property
    def feasible_components(self) -> List["Component"]:
        if self._feasible_components is None:
            raise RuntimeError(
                "Tried to access feasible_components without first calling fetch! "
                "Please fetch the feasible components before trying to access them."
            )

        return self._feasible_components

    @property
    def interfaces(self) -> List[Interface]:
        """Returns the interfaces available on this filter, if the filter is tied to a specific connectivity.

        Calling this on a filter that doesn't have a connectivity id set will raise an exception."""
        if not self.connectivity_id:
            raise RuntimeError(
                "Tried to access interfaces of a filter with no connectivity"
            )

        # From this point on we should be ok to assume that all feasible components share the same connectivity,
        # and therefore have the same interfaces

        if not self.feasible_components:
            raise RuntimeError(
                f"Filter {self} has no feasible components, cannot get interfaces!"
            )

        component = self.feasible_components[0]
        if component.connectivity_id != self.connectivity_id:
            raise RuntimeError(
                f"Filter {self} contains feasible component {component} belonging to a different connectivity!"
            )

        return [
            component_interface.interface
            for component_interface in component.interfaces
        ]

    def get_interface(
        self, interface_name: str, interface_type: InterfaceType
    ) -> Interface:
        """Return an interface from this filter's targeted connectivity.

        Will raise an exception if called on a filter without a connectivity."""
        for interface in self.interfaces:
            if (
                interface.name == interface_name
                and interface.interface_type == interface_type
            ):
                return interface

        raise KeyError(
            f"Interface with name {interface_name} and type {interface_type} does not exist!"
        )
