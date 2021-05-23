from collections import defaultdict, namedtuple
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Dict, List, Optional, Set, cast
from uuid import UUID

from cm.data.caching import cached
from cm.db import models
from cm.optimization import types as opt_types

from .interface_pin import InterfacePin

if TYPE_CHECKING:
    from cm.data.interface_family import InterfaceFamily

PinData = namedtuple("PinData", ["db_pin", "compatible_ids", "parent_ids"])


@dataclass(unsafe_hash=True)
class InterfaceType:
    """Analogous class to cm.db.models.InterfaceType."""

    id: UUID  # id of the corresponding models.interface object
    name: str
    label: str
    family: "InterfaceFamily"
    allow_child_interfaces: bool
    function: str
    can_be_required: bool
    can_be_specialised: bool
    pins: List[InterfacePin] = field(hash=False, repr=False, compare=False)
    children: List["InterfaceType"] = field(hash=False, repr=False, compare=False)
    parents: List["InterfaceType"] = field(hash=False, repr=False, compare=False)
    compatible_interface_types: List["InterfaceType"] = field(
        hash=False, repr=False, compare=False
    )

    # These id fields only exist because we have to populate ids first,
    # and then manually populate the fields with the right objects.
    # This is all to avoid creating the same types over and over.
    family_id: Optional[UUID] = field(repr=False)
    parent_ids: List[UUID] = field(hash=False, repr=False, compare=False)
    compatible_interface_type_ids: List[UUID] = field(
        hash=False, repr=False, compare=False,
    )

    @staticmethod
    def _placeholder_family() -> "InterfaceFamily":
        """When first constructing an interface type, we cannot create its family due to circular dependencies.

        This family is used as a placeholder until the correct family can be created.
        """
        from cm.data.interface_family import InterfaceFamily

        return InterfaceFamily(id=None, name="NONE", label="NONE", interface_types=[])

    @classmethod
    def _from_db(
        cls,
        db_interface_type: models.InterfaceType,
        pin_data: List[PinData],
        parent_ids: List[UUID],
        compatible_interface_type_ids: List[UUID],
    ) -> "InterfaceType":
        """Private method for creating interface types from db instances.

        This method, unlike most other from_db methods, isn't meant to be used directly.
        This is because interface types are all linked together, and it's much more efficient
        to just create and then cache all interface types along with their families together.

        To get an interface type from a db object, just run

        InterfaceType.get_all_as_dict()[db_interface_type.id]
        """

        # First create the raw pin objects without any related objects added, then populate those fields
        # We need to do this for _all_ interface pins, as we don't know yet which are compatible/related to this type.
        all_pins = {
            db_pin.id: InterfacePin._from_db(db_pin)
            for db_pin, compatible_ids, pin_parent_ids in pin_data
        }

        pins: List[InterfacePin] = []
        # Populate all related objects and remember which pins belong to this type

        for db_pin, compatible_ids, pin_parent_ids in pin_data:
            pin = all_pins[db_pin.id]
            pin.compatible_pins = [
                all_pins[compatible_id] for compatible_id in compatible_ids
            ]
            pin.parent_pins = [all_pins[parent_id] for parent_id in pin_parent_ids]

            # Assign the reverse side of the parent relation
            for parent in pin.parent_pins:
                parent.child_pins.append(pin)

            # If this pin belongs to the current interface type, remember it
            if pin.interface_type_id == db_interface_type.id:
                pins.append(pin)

        return cls(
            id=db_interface_type.id,
            name=db_interface_type.name,
            label=db_interface_type.label,
            allow_child_interfaces=db_interface_type.allow_child_interfaces,
            function=db_interface_type.function,
            can_be_required=db_interface_type.can_be_required,
            can_be_specialised=db_interface_type.can_be_specialised,
            pins=pins,
            # Temporary ids, these get be replaced with the real objects later
            family=cls._placeholder_family(),
            parents=[],
            children=[],
            compatible_interface_types=[],
            family_id=db_interface_type.family_id,
            parent_ids=parent_ids,
            compatible_interface_type_ids=compatible_interface_type_ids,
        )

    @staticmethod
    @cached(
        models.InterfaceType,
        models.InterfacePin,
        models.InterfaceFamily,
        timeout=60 * 60 * 24,
    )
    def get_all_as_dict() -> Dict[UUID, "InterfaceType"]:
        """Heavily cached helper method for the frequently needed job of getting all interface types."""
        from cm.data.interface_family import InterfaceFamily

        # The implementation of _from_db leaves interface families,
        # as well as compatible types, unpopulated. This is so we can avoid calling from_db
        # multiple times for the same objects.
        db_pins = models.InterfacePin.objects.all()

        # Get the pin compatibility data. We do this using the through table to save a boatload of queries
        compatible_pins: Dict[UUID, Set[UUID]] = defaultdict(set)
        for via in models.InterfacePin.compatible_pins.through.objects.all():
            compatible_pins[via.from_interfacepin_id].add(via.to_interfacepin_id)

        # Get the pin parent/child data. Same idea as above, using a query on the through table to save queries.
        pin_parents: Dict[UUID, Set[UUID]] = defaultdict(set)
        for via in models.InterfacePin.parent_pins.through.objects.all():
            pin_parents[via.from_interfacepin_id].add(via.to_interfacepin_id)

        pins = [
            PinData(
                db_pin=db_pin,
                compatible_ids=compatible_pins[db_pin.id],
                parent_ids=pin_parents[db_pin.id],
            )
            for db_pin in db_pins
        ]

        interface_types = {
            db_interface_type.id: InterfaceType._from_db(
                db_interface_type,
                pin_data=pins,
                parent_ids=list(
                    db_interface_type.parents.all().values_list("id", flat=True)
                ),
                compatible_interface_type_ids=db_interface_type.compatible_interface_types.all().values_list(
                    "id", flat=True
                ),
            )
            for db_interface_type in models.InterfaceType.objects.all()
        }

        # The implementation of InterfaceFamily._from_db does not populate the interface types for the same reason
        interface_families = {
            interface_family.id: interface_family
            for interface_family in [
                InterfaceFamily._from_db(db_interface_family,)
                for db_interface_family in models.InterfaceFamily.objects.all()
            ]
        }

        # Assign the interface families to the interface types and vice versa
        types_with_families = [t for t in interface_types.values() if t.family_id]
        for interface_type in types_with_families:
            interface_family = interface_families[cast(UUID, interface_type.family_id)]
            interface_type.family = interface_family
            interface_family.interface_types.append(interface_type)

        # All other types get an interface family that only contains the interface type itself
        types_without_families = [
            t for t in interface_types.values() if t not in types_with_families
        ]
        for interface_type in types_without_families:
            interface_family = InterfaceFamily(
                id=None,
                name=interface_type.name,
                label=interface_type.label,
                interface_types=[interface_type],
            )
            interface_type.family = interface_family

        # Assign parent/child relations and compatible interface types
        for interface_type in interface_types.values():
            for parent_id in interface_type.parent_ids:
                parent = interface_types[parent_id]
                parent.children.append(interface_type)
                interface_type.parents.append(parent)

            for (
                compatible_interface_type_id
            ) in interface_type.compatible_interface_type_ids:
                interface_type.compatible_interface_types.append(
                    interface_types[compatible_interface_type_id]
                )

        return interface_types

    @classmethod
    def get_all(cls) -> List["InterfaceType"]:
        """Heavily cached helper method for the frequently needed job of getting all interface types."""
        return list(cls.get_all_as_dict().values())

    @classmethod
    def get_all_as_optimization(cls) -> List[opt_types.InterfaceType]:
        """Heavily cached helper method for the frequently needed job
        of getting all interface types as optimization objects. """
        return [interface_type.to_optimization() for interface_type in cls.get_all()]

    def to_optimization(self) -> opt_types.InterfaceType:

        pins = [interface_pin.to_optimization() for interface_pin in self.pins]

        return opt_types.InterfaceType(
            id=self.id,
            name=self.name,
            interface_pins=pins,
            compatible_interface_type_ids=self.compatible_interface_type_ids,
        )

    @property
    def pin_dict(self) -> Dict[UUID, InterfacePin]:
        return {pin.id: pin for pin in self.pins}

    def get_pin_by_reference(self, pin_reference: str) -> InterfacePin:
        for pin in self.pins:
            if pin.reference == pin_reference:
                return pin
        raise KeyError(f"{self} has no interface pin with reference {pin_reference}")

    def __str__(self) -> str:
        return self.name

    __repr__ = __str__

    def is_compatible(self, other: "InterfaceType") -> bool:
        """Determine if a given interface type is compatible."""
        # FIXME: This isn't the correct way to check for interface type compatibility
        return (
            self in other.compatible_interface_types
            or other in self.compatible_interface_types
            or self in other.parents
            or other in self.parents
        )
