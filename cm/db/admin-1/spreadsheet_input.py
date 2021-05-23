import copy
import csv
import re
from collections import defaultdict
from io import StringIO
from typing import Any, Dict, List, Set

from django.core.exceptions import ValidationError
from django.db.models import Count

from cm.db.constants import PinType
from cm.db.models import (
    Connectivity,
    Interface,
    InterfacePin,
    InterfaceType,
    Pin,
    PinAssignment,
)


class SpreadsheetFormatError(Exception):
    pass


PIN_TABLE_CSV_SCHEMA = {
    "Pin Number": "pin_number",
    "Pin Name": "pin_name",
    "Pin Interface(s)": "pin_interfaces",
    "Vref": "voltage_reference",
}


def parse_csv(data, csv_schema, required_fields=None):
    """Parse a CSV according to the field mapping described by `csv_schema`.

    csv_schema is a dict of Column name to code-friendly field name.
    The field names are only used internally in this module.
    """
    required_fields = required_fields or csv_schema.keys()
    reader = csv.DictReader(StringIO(data), delimiter="\t")
    rows = [row for row in reader]
    if not rows:
        return

    errors = []
    for field_name in required_fields:
        if field_name not in rows[0]:
            errors.append(f"Missing required field {field_name}")
    if errors:
        raise ValidationError(errors)

    return [
        {
            csv_schema[field_name]: field_value
            for field_name, field_value in row.items()
            if field_name in csv_schema
        }
        for row in rows
    ]


def parse_interface_pins(
    row,
    interfaces_string,
    pin_number,
    interface_types,
    existing_sibling_interfaces=None,
    single_pin_interface_types=None,
    existing_offset_interfaces=None,
):
    """Return the interface pins for a specific connectivity pin in a dict indexed by interface name.

    It's allowed to use interface names without indexes (SPI instead of SPI0) in certain circumstances:

    For devices with a single pin, the pin _and_ index can be skipped, creating consecutively indexed interfaces.
    Example:
        DIG, DIG, DIG -> creates three digital interfaces, called DIG0, DIG1, DIG2.

    For devices with multiple pins, only the index may be skipped, creating a _single_ device.
    Skipping indexes if there is more than one device of the same type is an error, as we won't be able to match
    pins to devices.

    Pass in has_digital=True to add a digital interface to the pin even if not explicitly specified.
    """
    single_pin_interface_types = single_pin_interface_types or []
    existing_offset_interfaces = existing_offset_interfaces or []
    interface_strings = [s.strip() for s in interfaces_string.split("/") if s.strip()]
    interface_data = {}
    errors = []
    unidentified_data = []

    # Precalculate which interface types are single-pin ones so we only have to do it once
    single_pin_interface_types = [
        interface_type
        for interface_type in interface_types
        if interface_type.pins.count() == 1
    ]
    has_explicit_single_pin_interfaces = {
        interface_type: False for interface_type in single_pin_interface_types
    }

    interface_index_offsets = {}
    siblings_per_type: Dict[str, List[Interface]] = defaultdict(list)
    for interface_type in interface_types:
        # Precalculate index offsets due to existing parent devices
        highest_index = highest_interface_index(
            existing_offset_interfaces, interface_type
        )
        if highest_index is None:
            interface_index_offsets[interface_type.name] = 0
        else:
            interface_index_offsets[interface_type.name] = highest_index + 1

        # Precalculate the list of multi-pin sibling devices.  We need this because
        # when skipping indexes there can only ever be one multi-pin device of the same type in one group.
        siblings_of_same_type = [
            s for s in existing_sibling_interfaces if s.interface_type == interface_type
        ]
        for sibling_interface in siblings_of_same_type:
            siblings_per_type[sibling_interface.interface_type.name].append(
                sibling_interface
            )

    for interface_string in interface_strings:
        for interface_type in interface_types:
            is_single_pin_interface = interface_type in single_pin_interface_types
            m = re.fullmatch(interface_type.bulk_input_pattern, interface_string)
            if not m:
                continue
            data = m.groupdict()

            # Check if the interface name contains an interface index, or if we need to compute one
            # For single-pin devices we simply count up interface indexes with every pin we encounter
            # For multi-pin devices we have to assume all non-indexed pins belong to the same device.

            interface_name = data["name"]
            interface_channel = 0
            if interface_type.interface_bulk_input_pattern:
                interface_match = re.fullmatch(
                    interface_type.interface_bulk_input_pattern, interface_name
                )
                if not interface_match:
                    errors.append(
                        f"Interface {interface_name} doesn't match the bulk expression for {interface_type}!"
                    )
                    continue

                if interface_match.groupdict()["index"] in [None, ""]:
                    try:
                        # Increase the interface index by one if this is a new single-pin device,
                        # otherwise always use index 0 (plus an offset for parent interfaces).
                        index_offset = interface_index_offsets[interface_type.name]
                        highest_index = (
                            highest_interface_index(
                                existing_sibling_interfaces, interface_type
                            )
                            or 0
                        )
                        if is_single_pin_interface:
                            interface_index = highest_index + index_offset + 1
                        else:
                            # If there's already a sibling device of this type we use that,
                            # otherwise create a new index
                            siblings = siblings_per_type[interface_type.name]
                            if len(siblings) > 1:
                                raise ValidationError(
                                    f"More than one sibling found for {interface_name} without index"
                                )
                            elif len(siblings) == 1:
                                interface_index = siblings[0].interface_index
                            else:
                                interface_index = highest_index + index_offset

                    except ValidationError as e:
                        errors.append(str(e))
                        continue
                    interface_name = f"{interface_name}{interface_index}"

            if data.get("channel") is not None:
                interface_channel = int(data.get("channel"))  # type: ignore

            # Account for interfaces with a single pin, which don't need to specify the pin explicitly
            if data.get("pin"):
                pin_reference = data["pin"]
            else:
                if not is_single_pin_interface:
                    errors.append(
                        f"Pin {pin_number}: Missing interface pin reference on {interface_type}!"
                    )
                    continue
                pin_reference = interface_type.pins.first().reference

            if interface_type in single_pin_interface_types:
                has_explicit_single_pin_interfaces[interface_type] = True

            try:
                interface_data[interface_name] = {
                    "interface_pin": InterfacePin.objects.get(
                        interface_type=interface_type, reference=pin_reference
                    ),
                    "channel": interface_channel,
                }
            except InterfacePin.DoesNotExist:
                errors.append(
                    f"Pin {pin_number}: Interface type {interface_type} has no interface pin {data['pin']}!"
                )

            # We've processed this interface type, go to the next one
            break
        else:
            # We can't just raise an error if we can't identify an interface, as we'd likely get duplicated errors.
            # Instead we return the list of unidentified interfaces and let the calling function collate these.
            unidentified_data.append(interface_string)

    # Add any implicit single pin interfaces that were specified
    for single_pin_interface_type in single_pin_interface_types:
        if has_explicit_single_pin_interfaces[single_pin_interface_type]:
            # We added this interface explicitly, don't do it twice.
            continue

        column_name = f"has_{single_pin_interface_type.slug}"
        if column_name in row and parse_single_pin_interface_column(row[column_name]):
            highest_index = highest_interface_index(
                existing_sibling_interfaces, single_pin_interface_type
            )
            if highest_index is None:
                interface_index = 0
            else:
                interface_index = highest_index + 1
            interface_name = f"{single_pin_interface_type.label}{interface_index}"
            interface_data[interface_name] = InterfacePin.objects.get(
                interface_type=single_pin_interface_type,
            )

    return interface_data, errors, unidentified_data


def parse_single_pin_interface_column(digital_io_column):
    """Interpret the extra column which specifies if a pin has a digital I/O.

    This column does the exact same thing as specifying a digital interface in the interfaces column,
    it's purely a time-saving feature.
    """
    if digital_io_column is None:
        return False
    return digital_io_column.strip().lower() in ["y", "true", "1"]


def highest_interface_index(existing_sibling_interfaces, new_interface_type):
    existing_names_of_same_type = [
        i.name
        for i in existing_sibling_interfaces
        if i.interface_type == new_interface_type
    ]
    existing_indexes = []
    for interface_name in existing_names_of_same_type:
        m = re.fullmatch(
            new_interface_type.interface_bulk_input_pattern, interface_name
        )
        if not m:
            raise ValidationError(
                f"{interface_name} doesn't match its interface bulk expression, this should never happen!"
            )
        index = m.groupdict()["index"]
        if not index:
            continue
        existing_indexes.append(int(index))

    # Special case - if there are no indexes at all, return None.
    if not existing_indexes:
        return None

    return sorted(existing_indexes)[-1]


def get_bulk_interface_types():
    """Return all interface types compatible with bulk input."""
    return InterfaceType.objects.exclude(bulk_input_pattern="")


def calculate_pin_type(interface_name, pin_type, interface_pin):
    if pin_type:
        # FIXME: this is a massive hack, we need proper validation for pin type hierarchy.
        if pin_type == "analog" and interface_pin.pin_type == "digital":
            # If a pin is both digital and analog we always leave it as analog
            pass
        elif pin_type == "digital" and interface_pin.pin_type == "analog":
            # anlog overwrites digital
            pin_type = interface_pin.pin_type
        elif interface_pin.pin_type != pin_type:
            raise SpreadsheetFormatError(
                f"Pin {interface_pin} on interface {interface_name} doesn't match pin type {pin_type}!"
            )
    else:
        pin_type = interface_pin.pin_type

    return pin_type


def get_or_instantiate_interface(
    connectivity: Connectivity, interface_type: InterfaceType, interface_name: str
) -> Interface:
    """Get an interface from the db if it exists, otherwise instantiate (but don't save) a new interface."""
    try:
        pin_interface = (
            Interface.objects.get(
                name=interface_name,
                connectivity=connectivity,
                interface_type=interface_type,
            )
            if connectivity.pk
            else None
        )
    except Interface.DoesNotExist:
        pin_interface = None

    pin_interface = pin_interface or Interface(
        name=interface_name, connectivity=connectivity, interface_type=interface_type,
    )

    return pin_interface  # type: ignore


def process_connectivity_input(instance, spreadsheet_input, commit=False):
    """Parse pasted data from a spreadsheet containing pin and interface data.

    Pass commit=True to save the created objects to the database.

    Returns information about the pins and interfaces that were/would be created/updated in a dict:

    {
        'pins': [<pin instances>],
        'interfaces': [<interface instances>]
    }
    """
    if not spreadsheet_input:
        return

    interface_types = get_bulk_interface_types()

    csv_schema = copy.copy(PIN_TABLE_CSV_SCHEMA)
    # For the pin table, we allow specifying single-pin interfaces by using extra columns
    # These columns always have a name in the form of "Has <Interface Name>"
    for single_pin_interface_type in interface_types.annotate(
        pin_count=Count("pins")
    ).filter(pin_count=1):
        csv_schema[
            f"Has {single_pin_interface_type.name}"
        ] = f"has_{single_pin_interface_type.slug}"

    rows = parse_csv(
        spreadsheet_input, csv_schema, required_fields=PIN_TABLE_CSV_SCHEMA.keys()
    )
    if not rows:
        raise ValidationError("Couldn't extract any data!")
    errors: List[str] = []

    pins = []
    connectivity_interfaces: Dict[str, Interface] = {}
    interface_channels: Dict[Interface, int] = {}
    unidentified_interface_data: Set[str] = set([])
    # Data needed to construct pin assignments, per interface
    pin_assignment_data: Dict[Interface, List[Any]] = defaultdict(list)
    automatic_assignments: List[PinAssignment] = []

    for row in rows:
        pin_number = row["pin_number"]
        interface_pins_data, interface_errors, unidentifed_data = parse_interface_pins(
            row,
            row["pin_interfaces"] or "",
            pin_number,
            interface_types,
            existing_sibling_interfaces=list(connectivity_interfaces.values()),
        )
        errors += interface_errors
        unidentified_interface_data |= set(unidentifed_data)

        # Get or create the row's pin
        try:
            pin = (
                Pin.objects.get(number=pin_number, connectivity=instance)
                if instance.pk
                else None
            )
        except Pin.DoesNotExist:
            pin = None

        pin = pin or Pin(connectivity=instance, number=pin_number,)

        # Get or create the row's interfaces
        pin_type = None
        for interface_name, interface_pin_data in interface_pins_data.items():
            interface_pin = interface_pin_data["interface_pin"]
            interface_channel = interface_pin_data["channel"]
            # Set the pin type. We expect this to be the same for all interface pins
            try:
                pin_type = calculate_pin_type(interface_name, pin_type, interface_pin)
            except SpreadsheetFormatError as e:
                errors.append(str(e))
                continue

            interface_type = interface_pin.interface_type
            if interface_name in connectivity_interfaces:
                if (
                    connectivity_interfaces[interface_name].interface_type
                    != interface_type
                ):
                    errors.append(
                        f"Found two interfaces with name {interface_name} but different types!"
                    )
                # We've already seen this interface on another pin, no need to construct it again
                pin_interface = connectivity_interfaces[interface_name]
            else:
                pin_interface = get_or_instantiate_interface(
                    instance, interface_type, interface_name
                )

                connectivity_interfaces[interface_name] = pin_interface

            # Remember the interface and interface pin to construct pin assignments later
            pin_assignment_data[pin_interface].append(
                {
                    "interface_pin": interface_pin,
                    "pin": pin,
                    "channel": interface_channel,
                }
            )
            interface_channels[pin_interface] = max(
                interface_channels.get(pin_interface, 1), interface_channel + 1
            )

        # Update the remaining fields on the pin instance
        pin.name = row["pin_name"]
        pin.pin_type = pin_type or ""
        # Remember just the name of the vref for now, we assign this properly later when all pins are created
        pin._vref_name = row["voltage_reference"] or None
        pins.append(pin)

    # Do any global validation here
    # Validate pin assignments. we expect each interface_pin to be assigned just once, and we expect
    # all pins of the interface type to be used
    for unidentified_interface in unidentified_interface_data:
        errors.append(
            f"Couldn't identify interface from string '{unidentified_interface}'"
        )

    for interface, interface_assignments in pin_assignment_data.items():
        interface_type = interface.interface_type
        interface_pins = interface_type.pins.all()

        assignment_counts: Dict[str, int] = defaultdict(int)
        for assignment in interface_assignments:
            assignment_counts[assignment["interface_pin"]] += 1

        for interface_pin in interface_pins:
            count = assignment_counts[interface_pin]
            if (
                not count
                and interface_pin.is_required
                and not interface_pin.create_automatically
            ):
                errors.append(
                    f"Required Interface pin {interface_pin.reference} not used in interface {interface}!"
                )

    # Validate vref interfaces
    for pin in pins:
        if pin._vref_name and pin._vref_name not in connectivity_interfaces:
            errors.append(
                f"Cannot find vref interface with name {pin._vref_name} for pin {pin}!"
            )

    if commit and not errors:
        # Save all the data, in the correct order to make sure objects are created correctly
        for interface in connectivity_interfaces.values():
            # Set the interface count on the interface before saving it, as that will be used to validate the channels
            interface.channels = interface_channels.get(interface, 1)
            interface.save()

        # Sort the pins to make sure that power pins are saved first, as other pins might reference them as
        # voltage references
        def _pin_order(pin):
            if pin.pin_type == PinType.power:
                return -1
            return 0

        for pin in sorted(pins, key=_pin_order):
            if pin._vref_name:
                pin.voltage_reference = connectivity_interfaces[pin._vref_name]
            pin.save()

        # Create the pin assignments
        for interface, interface_assignments in pin_assignment_data.items():
            for assignment in interface_assignments:
                PinAssignment.objects.update_or_create(
                    interface=interface,
                    interface_pin=assignment["interface_pin"],
                    pin_identifiers=assignment["pin"].number,
                    defaults={"channel": assignment["channel"]},
                )

            # Check if any missing assignments for this interface should be created automatically
            missing_interface_pins = set(
                interface.interface_type.pins.filter(create_automatically=True)
            ) - set(
                interface_assignment["pin"]
                for interface_assignment in interface_assignments
            )
            # Create any missing assignments that are configured to be created automatically
            for interface_pin in missing_interface_pins:
                automatic_assignments.append(
                    PinAssignment.objects.update_or_create(
                        interface=interface,
                        interface_pin=interface_pin,
                        pin_identifiers="*",
                    )[0]
                )

    # Delete any old pins and interfaces that weren't defined in the newly submitted data
    # Note this will also take care of deleting stale pin assignments
    if commit and instance.pk and not errors:
        Pin.objects.filter(connectivity=instance).exclude(
            pk__in=[p.pk for p in pins]
        ).delete()

        Interface.objects.filter(connectivity=instance).exclude(
            pk__in=[i.pk for i in connectivity_interfaces.values()]
        ).delete()

    if errors:
        raise ValidationError({"pin_spreadsheet_input": errors})

    return {
        "pins": pins,
        "interfaces": connectivity_interfaces,
        "automatic_assignments": automatic_assignments,
    }
