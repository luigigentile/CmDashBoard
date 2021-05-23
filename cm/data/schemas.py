import re
from typing import TYPE_CHECKING, Any, Callable, Dict, List, cast
from uuid import UUID

from django.db.models import QuerySet

from cm import constants
from cm.data import ranges, units
from cm.data.decorators import validator
from cm.data.pin import Pin
from cm.data.schema import DictField, Field, IgnoreField, ListField, Schema
from cm.data.serializable import registry
from cm.db import models, query
from cm.exceptions import ValidationError

mm = units.UNITS("mm")

if TYPE_CHECKING:
    from cm.data.component.filter import ComponentFilter


def _replace_key(d: Dict[str, Any], key: str, replacement: Any) -> Dict[str, Any]:
    """Replace d[key] with a new value."""
    return {
        **d,
        key: replacement,
    }


def _parse_layer_range(raw_value: str) -> ranges.NumberRange:
    """Parse an allowed layer range from allowed raw data. Default is up to 16 layers.

    The number of layers has to be positive and either 1 or an even number

    We will always specify the layers as a discrete range, but we let users
    specify a continuous range for simplicity. I.e. we interpret "layers: 1..8" as "1,2,4,6,8".
    """
    errors: List[str] = []

    try:
        layer_range = ranges.parse_number_range(raw_value)
    except ValueError as e:
        raise ValidationError(str(e))

    if (
        layer_range.low % 2
        and layer_range.low != 1
        or layer_range.high % 2
        and layer_range.high != 1
    ):
        errors.append(
            f"Layer counts have to be even (or 1). Got {layer_range.low}..{layer_range.high}"
        )
    if layer_range.high > 100:
        errors.append(f"A maximum of 100 layers is supported, got {layer_range.high}!")
    if layer_range.low <= 0:
        errors.append(f"Layers cannot be zero or negative, got {layer_range.low}!")
    if layer_range.is_continuous:
        # Turn a continuous range into a discrete one

        # If the upper limit is one layer, just return a range from 1 to 1
        if layer_range.high == 1:
            layer_list = [1]
        else:
            # We include "1" exactly if the lower limit is 1, 1 is a special case because it's not even.
            layer_list = [1] if layer_range.low == 1 else []
            # Now we add all the even numbers from layer_range.low to layer_range.high.
            layer_list += list(
                range(max(2, int(layer_range.low)), int(layer_range.high) + 2, 2)
            )
        layer_range = ranges.DiscreteNumberRange(layer_list)
    else:
        for value in cast(ranges.DiscreteRange, layer_range).values:
            if value % 2 and value != 1:
                errors.append(f"Layer counts have to be even (or 1), got {int(value)}!")

    if errors:
        raise ValidationError(errors)

    return layer_range


def _parse_filter(reference: str, filter_data: Dict[str, Any]) -> "ComponentFilter":
    from cm.data.component.filter import ComponentFilter

    category = models.Category.objects.get(slug=filter_data.pop("category"))

    filter_id = filter_data.pop("id", None)
    if filter_id:
        filter_id = UUID(filter_id)
    links = filter_data.pop("links", None)
    if links:
        links = {UUID(link_id) for link_id in links}

    return ComponentFilter(
        filter_id=filter_id,
        reference=reference,
        reference_label=reference[0],
        category_id=category.id,
        queryset=query.blocks(category=category, **filter_data),
        links=links,
    )


def _matches_regex(regex: str) -> Callable[[Any], bool]:
    def wrapped(value: Any) -> bool:
        return bool(re.match(regex, value))

    return wrapped


def SPEC_SCHEMA() -> Schema:
    from cm.data.component import Component

    return Schema(
        [
            Field("name", str),
            Field("number_of_boards", int),
            Field("architecture_strategy", str, default=constants.DEFAULT_ARCHITECTURE),
            Field(
                "maximum_price",
                float,
                validator=validator(
                    lambda v: bool(v >= 0), "Maximum price cannot be negative, got {v}"
                ),
                default=10000,
            ),
            Field(
                "width",
                lambda v: ranges.parse_quantity_range(v, context=units.LENGTH),
                validator=validator(
                    lambda v: bool(v.low >= 0 * mm),
                    "Width cannot be negative, got {v.low}",
                ),
                default=ranges.ContinuousQuantityRange(
                    0 * mm, float("inf") * mm, context=units.LENGTH
                ),
                value_type=ranges.Range,
            ),
            Field(
                "height",
                lambda v: ranges.parse_quantity_range(v, context=units.LENGTH),
                validator=validator(
                    lambda v: bool(v.low >= 0 * mm),
                    "Height cannot be negative, got {v.low}",
                ),
                default=ranges.ContinuousQuantityRange(
                    0 * mm, float("inf") * mm, context=units.LENGTH
                ),
                value_type=ranges.Range,
            ),
            Field(
                "layers",
                _parse_layer_range,
                default=ranges.DiscreteNumberRange([1] + list(range(2, 16 + 2, 2))),
                value_type=ranges.DiscreteNumberRange,
            ),
            Field(
                "root_component",
                # Components is a bit of a special case, because we construct an ad-hoc component and then include the
                # children provided in the raw data. This means we have to do a bit more work here than usual.
                # Spec.components contains the list of children of this component, but not the component itself.
                lambda v: Component(
                    component_id=Component.generate_id(),
                    filter_id=Component.generate_id(),
                    reference="ROOT1",
                    function="root",
                    block=None,
                    children=[
                        _parse_filter(reference, filter_data)
                        for reference, filter_data in v.items()
                    ],
                    interfaces=[],
                    active_pin_uses={},
                    external_bus_requirements=[],
                    pins=[],
                ),
                raw_name="components",
                value_type=Component,
            ),
            DictField("schematics", list, default={}),
            DictField("boards", list, default={}),
            ListField("nets", registry["net.Net"], default=[]),
            ListField(
                "traces",
                lambda trace_data, validated_data: registry["trace.Trace"].from_data(
                    _replace_key(
                        trace_data,
                        "net",
                        registry["net.Net"].match_net(  # type: ignore
                            validated_data["nets"], trace_data["net"]
                        ),
                    )
                ),
                requires_validated_data=True,
                value_type=registry["trace.Trace"],
                default=[],
            ),
            DictField(
                "placements", registry["placement.Placement"], raw_name="placement",
            ),
            DictField("optimization_weights", lambda v: float(v), value_type=float),
            ListField("warnings", set, default=set()),
        ],
        processing_order=["name", "root_component", "nets", "traces"],
        required_fields=["name"],
    )


CONNECTORS_SPEC_SCHEMA = Schema(
    [Field("type", str), Field("series", str), Field("pins", int)]
)


def _parse_interface_pins(
    interface_name: str, raw_interface_pins: List[str], available_pins: List[Pin]
) -> List[Pin]:
    """Parse and validate interface pins.

    Interfaces that are defined on components get passed just a list of pin names.
    We need to compare these pin names with the pins that are available on the component and return
    the actual pin instances, so that the Interface can contain fully defined pins, not just their names.
    """
    available_pins = (
        available_pins or []
    )  # In some cases of invalid data, this can be None
    pins = []
    for pin_name in raw_interface_pins or []:
        for p in available_pins:
            if p.name == pin_name:
                pins.append(p)
                break
        else:
            raise ValidationError(
                f"Interface {interface_name} needs unavailable pin {pin_name}!"
            )
    return pins


def COMPONENT_SCHEMA() -> Schema:
    from cm.data.component import Component

    return Schema(
        [
            Field("reference", str),
            Field(
                "block",
                lambda v: models.Block.objects.get(id=v),
                value_type=models.Block,
            ),
            Field(
                # FIXME: sub-circuits are still unsupported here
                "children",
                lambda v: None,
                value_type=Component,
            ),
            IgnoreField(
                "external_bus_requirements", registry["bus_fragment.BusFragment"]
            ),
        ]
    )


def COMPONENT_FILTER_SCHEMA() -> Schema:
    return Schema(
        [
            Field(
                "reference",
                str,
                validator=validator(
                    _matches_regex(r".*[^\d]+[\d]+"),
                    "Component references have to be formatted as <identifier><number>, e.g. R1, U7, OSC97",
                ),
            ),
            Field("reference_label", str,),
            Field(
                "category_id",
                lambda v: models.Category.objects.get(slug=v).values_list(
                    "id", flat=True
                ),
                value_type=UUID,
                raw_name="category",
            ),
            Field("connectivity_id", str, default=None),
            Field(
                "queryset", QuerySet, default=models.Block.objects.all()
            ),  # specifying a queryset isn't supported
        ],
        required_fields=["reference"],
    )


def BUS_FRAGMENT_SCHEMA() -> Schema:
    return Schema(
        [
            Field("from_filter", registry["bus_fragment.BusFragment"], raw_name="from"),
            Field("to_filter", registry["bus_fragment.BusFragment"], raw_name="to"),
            Field(
                "interface_type",
                lambda v: models.InterfaceType.objects.get(name=v),
                value_type=models.InterfaceType,
            ),
            Field(
                "interface",
                lambda v: models.Interface.objects.get(name=v),
                value_type=models.Interface,
            ),
        ]
    )


VERTEX2D_SCHEMA = Schema(
    [Field("x", units.parser(units.LENGTH)), Field("y", units.parser(units.LENGTH)),]
)


def DRILL_SCHEMA() -> Schema:
    from cm.data.vector import Vector

    return Schema(
        [
            Field("center", Vector),
            Field("diameter", units.Quantity),
            Field("is_plated", bool),
        ]
    )


def VIA_SCHEMA() -> Schema:
    from cm.data.vector import Vector

    return Schema(
        [
            Field("center", Vector),
            Field("diameter", units.Quantity),
            Field("ring_diameter", units.Quantity),
            Field("from_layer", int),
            Field("to_layer", int),
        ]
    )


def PAD_SCHEMA() -> Schema:
    from cm.data.shapes import Shape

    return Schema(
        [
            Field("name", str),
            Field("drill", registry["layout.Drill"]),
            Field("shape", Shape),
        ]
    )


def SHAPE_LAYER_SCHEMA() -> Schema:
    from cm.data.shapes import Shape

    return Schema([ListField("shapes", Shape),])


def VIA_LAYER_SCHEMA() -> Schema:
    return Schema([ListField("vias", registry["layout.Via"]),])


def DRILL_LAYER_SCHEMA() -> Schema:
    return Schema([ListField("drills", registry["layout.Drill"])])


def VERTEX_LAYER_SCHEMA() -> Schema:
    return Schema([ListField("vertices", registry["layout.Vertex2D"]),])


def PAD_LAYER_SCHEMA() -> Schema:
    return Schema([ListField("pads", registry["layout.Pad"]),])


def LAYOUT_SCHEMA() -> Schema:
    return Schema(
        [
            ListField("copper", registry["layout.ShapeLayer"]),
            Field("dimension", registry["layout.ShapeLayer"]),
            Field("pads", registry["layout.ShapeLayer"]),
            Field("via", registry["layout.ViaLayer"]),
            Field("drill", registry["layout.DrillLayer"]),
            Field("mill", registry["layout.ShapeLayer"]),
            ListField("smd", registry["layout.ShapeLayer"]),
            ListField("silkscreen", registry["layout.ShapeLayer"]),
            ListField("mask", registry["layout.ShapeLayer"]),
            ListField("paste", registry["layout.ShapeLayer"]),
            ListField("glue", registry["layout.ShapeLayer"]),
            ListField("test", registry["layout.VertexLayer"]),
            ListField("keepout", registry["layout.ShapeLayer"]),
            ListField("documentation", registry["layout.ShapeLayer"]),
            ListField("internal_documentation", registry["layout.ShapeLayer"]),
        ]
    )


def TRACE_SCHEMA() -> Schema:
    return Schema(
        [
            Field("net", registry["net.Net"]),
            Field("layer", int),
            ListField("vertices", registry["layout.Vertex2D"]),
        ]
    )


NET_SCHEMA = Schema([Field("name", str), ListField("nodes", str),])


PLACEMENT_SCHEMA = Schema(
    [
        Field("y", units.parser(units.LENGTH)),
        Field("x", units.parser(units.LENGTH)),
        Field("rotation", units.parser(units.ANGLE)),
    ]
)
