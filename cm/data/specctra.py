from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union

from cm.data import units, vector
from cm.data.lisp import LispSerializable
from cm.data.schema import Field, IgnoreField, ListField, Schema


# A few helper functions
def _parse_specctra_bool(value: str) -> bool:
    return value.lower() == "on"


def _parse_specctra_vertex(raw_vertex: Dict[str, str]) -> "Vertex":
    """Parse a raw specctra vertex into a proper vertex instance."""
    return Vertex(float(raw_vertex["x"]), float(raw_vertex["y"]))


def _parse_specctra_length(raw_length: str) -> float:
    """Parse a unitless length from a specctra file. """
    return float(raw_length)


class SpecctraField(LispSerializable):
    @classmethod
    def get_serializer(cls, value: Any) -> Callable[[Any], Any]:
        # We overwrite the standard serializer just to add a few more strict checks.
        # There are a few internal data types that should never show up in a specctra file,
        # and we use the serializer here to validate that. This is purely defensive programming, added
        # because it's very easy to forgot to convert a quantity to a float when converting to specctra, for example.

        if isinstance(value, units.Quantity):
            raise RuntimeError(
                "Specctra field received a quantity object. This should never happen, specctra only uses floats!"
            )

        return super().get_serializer(value)


# Type Aliases
Shape = Union["Path", "Polygon", "Rectangle", "Circle"]
Rule = Union["WidthRule", "ClearanceRule"]
CircuitRule = Union["UseViaCircuitRule"]

# Constants


class WireType(Enum):
    FIX = "fix"
    ROUTE = "route"
    NORMAL = "normal"
    PROTECT = "protect"


class PcbSide(Enum):
    FRONT = "front"
    BACK = "back"


class LayerType(Enum):
    SIGNAL = "signal"
    POWER = "power"
    MIXED = "mixed"
    JUMPER = "jumper"


# Specctra types
@dataclass(init=False)
class Vertex(vector.Vector, SpecctraField):
    LISP_SCHEMA = ["x", "y"]
    SCHEMA = Schema(
        [
            Field("x", _parse_specctra_length, default=0, serialize_default=True),
            Field("y", _parse_specctra_length, default=0, serialize_default=True),
        ]
    )

    x: float = 0
    y: float = 0


@dataclass
class Path(SpecctraField):
    LISP_SCHEMA = ["layer_id", "aperture_width", "[[2]vertices]"]
    SCHEMA = Schema(
        [
            Field("layer_id", str),
            Field("aperture_width", float),
            ListField("vertices", _parse_specctra_vertex),
        ]
    )

    layer_id: str
    aperture_width: float
    vertices: List[Vertex]


@dataclass
class Polygon(SpecctraField):
    LISP_SCHEMA = ["layer_id", "aperture_width", "[[2]vertices]"]
    SCHEMA = Schema(
        [
            Field("layer_id", str),
            Field("aperture_width", float),
            ListField("vertices", _parse_specctra_vertex),
        ]
    )

    layer_id: str
    aperture_width: float
    vertices: List[Vertex]
    # aperture_type: round/square (default round)

    # Notes:
    # for regions, aperture_width must be 0


@dataclass
class Rectangle(SpecctraField):
    LISP_SCHEMA = ["layer_id", "x1", "y1", "x2", "y2"]
    SCHEMA = Schema(
        [
            Field("layer_id", str),
            Field("x1", _parse_specctra_length),
            Field("y1", _parse_specctra_length),
            Field("x2", _parse_specctra_length),
            Field("y2", _parse_specctra_length),
        ]
    )
    layer_id: str
    x1: float
    y1: float
    x2: float
    y2: float


@dataclass
class Circle(SpecctraField):
    LISP_SCHEMA = ["layer_id", "diameter", "?x", "?y"]
    SCHEMA = Schema(
        [
            Field("layer_id", str),
            Field("diameter", _parse_specctra_length),
            Field("x", _parse_specctra_length),
            Field("y", _parse_specctra_length),
        ]
    )
    layer_id: str
    diameter: float
    x: float = 0
    y: float = 0


@dataclass
class Wire(SpecctraField):
    LISP_SCHEMA = ["{rect|path|circle|polygon}", "?{net}", "?{type}"]
    SCHEMA = Schema(
        [
            Field("rectangle", Rectangle, raw_name="rect"),
            Field("path", Path),
            Field("circle", Circle),
            Field("polygon", Polygon),
            Field("net_id", str, raw_name="net"),
            Field("wire_type", WireType, raw_name="type"),
        ]
    )

    net_id: str
    wire_type: WireType = WireType.NORMAL
    rectangle: Optional[Rectangle] = None
    path: Optional[Path] = None
    circle: Optional[Circle] = None
    polygon: Optional[Polygon] = None

    # Unimplemented attributes:

    # turret
    # attr
    #     test / fanout / bus / jumper
    # shield
    #     net_id
    # [window]
    #     shape
    # connect
    #     terminal
    #         object_type ???
    #         pin_reference
    # supply

    @property
    def shape(self) -> Shape:
        shape = self.rectangle or self.path or self.circle or self.polygon
        if not shape:
            raise RuntimeError(f"{self} is missing a shape!")
        return shape

    @shape.setter
    def shape(self, new_shape: Shape) -> None:
        if isinstance(new_shape, Rectangle):
            self.rectangle = new_shape
        elif isinstance(new_shape, Path):
            self.path = new_shape
        elif isinstance(new_shape, Circle):
            self.circle = new_shape
        elif isinstance(new_shape, Polygon):
            self.polygon = new_shape
        else:
            raise RuntimeError(f"Unknown shape {new_shape}!")


@dataclass
class Wiring(SpecctraField):
    LISP_SCHEMA = ["[{wire}]"]
    SCHEMA = Schema([ListField("wires", Wire, raw_name="wire")])
    wires: List[Wire]

    # unit or resolution or null
    # test points
    # [supply pin]
    #     [pin_reference]
    #     net
    #         net_id


@dataclass
class UseViaCircuitRule(SpecctraField):
    LISP_SCHEMA = ["[padstack_ids]"]
    SCHEMA = Schema([ListField("padstack_ids", str)])

    padstack_ids: List[str]


@dataclass
class Circuit(SpecctraField):
    LISP_SCHEMA = ["{use_via}"]  # Note this is missing a _load_ of other options
    SCHEMA = Schema([Field("circuit_rules", UseViaCircuitRule, raw_name="use_via"),])

    circuit_rules: List[CircuitRule]


@dataclass
class ClearanceType(SpecctraField):
    LISP_SCHEMA = ["name", "?{layer_depth}"]
    SCHEMA = Schema([Field("name", str), Field("layer_depth", int),])

    name: str
    layer_depth: Optional[int] = None  # only for type buried_via_gap


@dataclass
class WidthRule(SpecctraField):
    LISP_SCHEMA = ["width"]
    SCHEMA = Schema([Field("width", float),])
    width: float


@dataclass
class ClearanceRule(SpecctraField):
    LISP_SCHEMA = ["clearance", "?{type}"]
    SCHEMA = Schema(
        [
            Field("clearance", float),
            Field("clearance_type", ClearanceType, raw_name="type"),
        ]
    )

    clearance: float
    clearance_type: Optional[ClearanceType]


@dataclass
class Rules(SpecctraField):
    LISP_SCHEMA = ["[{width|clearance}]"]
    SCHEMA = Schema(
        [ListField("width", WidthRule), ListField("clearance", ClearanceRule)]
    )
    width: List[WidthRule]
    clearance: List[ClearanceRule]


@dataclass
class NetClass(SpecctraField):
    LISP_SCHEMA = ["class_id", "[net_id]", "?{circuit}", "?{rule}"]
    SCHEMA = Schema(
        [
            Field("class_id", str),
            ListField("net_ids", str, raw_name="net_id"),
            Field("circuit", Circuit),
            Field("rules", Rules, raw_name="rule"),
        ]
    )
    class_id: str
    net_ids: List[str]
    circuit: Circuit
    rules: Rules

    # [layer rule]
    # topology


@dataclass
class Net(SpecctraField):
    LISP_SCHEMA = ["net_id", "{pins}"]
    SCHEMA = Schema([Field("net_id", str), ListField("pins", str),])
    net_id: str
    pins: List[str]  # Pin references, e.g. U1-23 (<part>-<pin>)

    # unassigned
    # net_number
    # type
    #   fix / normal
    # user_property
    # circuit
    # rule
    # [layer rule]
    # fromto
    # expose
    # noexpose
    # source
    # load
    # ancillaries
    # supply


@dataclass
class Network(SpecctraField):
    LISP_SCHEMA = ["[{net}]", "[{class}]"]
    SCHEMA = Schema(
        [
            ListField("nets", Net, raw_name="net"),
            ListField("classes", NetClass, raw_name="class"),
        ]
    )
    nets: List[Net]
    classes: List[NetClass]

    # [class_class]??
    # [group]
    # [group set]
    # [pair]
    # [bundle]
    #    bundle_id


@dataclass
class PinReference(SpecctraField):
    LISP_SCHEMA = ["pin_id", "[2]vertex"]
    SCHEMA = Schema(
        [
            Field("pin_id", str),
            Field("position", _parse_specctra_vertex, raw_name="vertex"),
        ]
    )
    pin_id: str
    position: Vertex


@dataclass
class Pin(SpecctraField):
    LISP_SCHEMA = ["padstack_id", "?{rotate}", "[3]reference"]
    SCHEMA = Schema(
        [
            Field("padstack_id", str),
            Field("reference", PinReference),
            Field("rotate", float),
        ]
    )
    padstack_id: str
    reference: PinReference
    rotate: float = 0

    # pin_array
    # user_property


@dataclass
class Outline(SpecctraField):
    LISP_SCHEMA = ["{rect|path|circle|polygon}"]
    SCHEMA = Schema(
        [
            Field("rectangle", Rectangle, raw_name="rect"),
            Field("path", Path),
            Field("circle", Circle),
            Field("polygon", Polygon),
        ]
    )
    rectangle: Optional[Rectangle] = None
    path: Optional[Path] = None
    circle: Optional[Circle] = None
    polygon: Optional[Polygon] = None

    @property
    def shape(self) -> Shape:
        shape = self.rectangle or self.path or self.circle or self.polygon
        if not shape:
            raise RuntimeError(f"{self} is missing a shape!")
        return shape

    @shape.setter
    def shape(self, new_shape: Shape) -> None:
        if isinstance(new_shape, Rectangle):
            self.rectangle = new_shape
        elif isinstance(new_shape, Path):
            self.path = new_shape
        elif isinstance(new_shape, Circle):
            self.circle = new_shape
        elif isinstance(new_shape, Polygon):
            self.polygon = new_shape
        else:
            raise RuntimeError(f"Unknown shape {new_shape}!")


@dataclass
class Image(SpecctraField):
    LISP_SCHEMA = ["image_id", "[{outline}]", "[{pin}]"]
    SCHEMA = Schema(
        [
            Field("image_id", str),
            ListField("outlines", Outline, raw_name="outline"),
            ListField("pins", Pin, raw_name="pin"),
        ]
    )
    image_id: str
    outlines: List[Outline]
    pins: List[Pin]

    # side
    # unit
    # [conductor shape]
    # [conductor via]
    # rule
    # place rule
    # [keepout]
    # image property


@dataclass
class PadstackShape(SpecctraField):
    LISP_SCHEMA = ["{rect|path|circle|polygon}", "?{connect}"]
    SCHEMA = Schema(
        [
            Field("rectangle", Rectangle, raw_name="rect"),
            Field("path", Path),
            Field("circle", Circle),
            Field("polygon", Polygon),
            Field("connect", _parse_specctra_bool),
        ]
    )
    connect: bool = True
    rectangle: Optional[Rectangle] = None
    path: Optional[Path] = None
    circle: Optional[Circle] = None
    polygon: Optional[Polygon] = None
    # window

    @property
    def shape(self) -> Shape:
        shape = self.rectangle or self.path or self.circle or self.polygon
        if not shape:
            raise RuntimeError(f"{self} is missing a shape!")
        return shape

    @shape.setter
    def shape(self, new_shape: Shape) -> None:
        if isinstance(new_shape, Rectangle):
            self.rectangle = new_shape
        elif isinstance(new_shape, Path):
            self.path = new_shape
        elif isinstance(new_shape, Circle):
            self.circle = new_shape
        elif isinstance(new_shape, Polygon):
            self.polygon = new_shape
        else:
            raise RuntimeError(f"Unknown shape {new_shape}!")


@dataclass
class Padstack(SpecctraField):
    LISP_SCHEMA = ["padstack_id", "[{shape}]", "?{attach}", "?{rotate}", "?{absolute}"]
    SCHEMA = Schema(
        [
            Field("padstack_id", str),
            ListField("shapes", PadstackShape, raw_name="shape"),
            Field("attach", _parse_specctra_bool),
            Field("rotate", _parse_specctra_bool),
            Field("absolute", _parse_specctra_bool),
        ]
    )
    padstack_id: str
    shapes: List[PadstackShape]
    attach: bool = True
    rotate: bool = True
    absolute: bool = False

    # unit
    # attach has a weird extra subattribute "use via"
    # pad_via_site
    # rule


@dataclass
class Library(SpecctraField):
    LISP_SCHEMA = ["?[{image}]", "[{padstack}]"]
    SCHEMA = Schema(
        [
            ListField("images", Image, raw_name="image"),
            ListField("padstacks", Padstack, raw_name="padstack"),
        ]
    )
    images: List[Image]
    padstacks: List[Padstack]

    # unit
    # [jumper]
    # directory
    # extra_image_directory
    # [family_family]??
    # [image_image]??


@dataclass
class PartNumber(SpecctraField):
    LISP_SCHEMA = ["part_number"]
    SCHEMA = Schema([Field("part_number", str),])

    part_number: str


@dataclass
class PlacementReference(SpecctraField):
    LISP_SCHEMA = ["component_id", "[2]vertex", "side", "rotation", "?{PN}"]
    SCHEMA = Schema(
        [
            Field("component_id", str),
            Field("position", _parse_specctra_vertex, raw_name="vertex"),
            Field("side", PcbSide),
            Field("rotation", float),
            Field("pn", PartNumber, raw_name="PN"),
        ]
    )

    component_id: str
    position: Vertex
    side: PcbSide
    rotation: float
    pn: PartNumber

    # mirror
    # component status
    # logical part
    # place rule
    # component property
    # lock type
    #   position gate subgate pin
    # rule or region


@dataclass
class Component(SpecctraField):
    LISP_SCHEMA = ["image_id", "[{place}]"]
    SCHEMA = Schema([Field("image_id", str), ListField("place", PlacementReference),])
    image_id: str
    place: List[PlacementReference]


@dataclass
class Quantity(SpecctraField):
    LISP_SCHEMA = ["unit", "magnitude"]
    SCHEMA = Schema([Field("unit", str), Field("magnitude", float),])

    unit: str
    magnitude: float


@dataclass
class Placement(SpecctraField):
    LISP_SCHEMA = ["?{resolution}", "[{component}]"]
    SCHEMA = Schema(
        [
            Field("resolution", Quantity),
            ListField("components", Component, raw_name="component"),
        ]
    )
    components: List[Component]
    resolution: Optional[Quantity] = None

    # unit or resolution
    # place control


@dataclass
class LayerProperties(SpecctraField):
    LISP_SCHEMA = ["{index}"]
    SCHEMA = Schema([Field("index", int)])
    # This class takes a bit of artistic license encoding frequently used properties.
    # In reality, these properties are user-defined.
    index: int


@dataclass
class Layer(SpecctraField):
    LISP_SCHEMA = ["name", "{type}", "{property}"]
    SCHEMA = Schema(
        [
            Field("name", str),
            Field("layer_type", LayerType, raw_name="type"),
            Field("properties", LayerProperties, raw_name="property"),
        ]
    )

    name: str
    layer_type: LayerType
    properties: LayerProperties


@dataclass
class Plane(SpecctraField):
    LISP_SCHEMA = ["name", "{rect|path|circle|polygon}"]
    SCHEMA = Schema(
        [
            Field("name", str),
            Field("rectangle", Rectangle, raw_name="rect"),
            Field("path", Path),
            Field("circle", Circle),
            Field("polygon", Polygon),
        ]
    )
    net_id: str
    rectangle: Optional[Rectangle] = None
    path: Optional[Path] = None
    circle: Optional[Circle] = None
    polygon: Optional[Polygon] = None
    # window

    @property
    def shape(self) -> Shape:
        shape = self.rectangle or self.path or self.circle or self.polygon
        if not shape:
            raise RuntimeError(f"{self} is missing a shape!")
        return shape

    @shape.setter
    def shape(self, new_shape: Shape) -> None:
        if isinstance(new_shape, Rectangle):
            self.rectangle = new_shape
        elif isinstance(new_shape, Path):
            self.path = new_shape
        elif isinstance(new_shape, Circle):
            self.circle = new_shape
        elif isinstance(new_shape, Polygon):
            self.polygon = new_shape
        else:
            raise RuntimeError(f"Unknown shape {new_shape}!")


@dataclass
class Boundary(SpecctraField):
    LISP_SCHEMA = ["{rect|path}"]
    SCHEMA = Schema(
        [Field("rectangle", Rectangle, raw_name="rect"), Field("path", Path),]
    )
    rectangle: Optional[Rectangle] = None
    path: Optional[Path] = None

    # rule

    @property
    def shape(self) -> Union[Path, Rectangle]:
        shape = self.rectangle or self.path
        if not shape:
            raise RuntimeError(f"{self} is missing a shape!")
        return shape

    @shape.setter
    def shape(self, new_shape: Union[Path, Rectangle]) -> None:
        if isinstance(new_shape, Rectangle):
            self.rectangle = new_shape
        elif isinstance(new_shape, Path):
            self.path = new_shape
        else:
            raise RuntimeError("Boundary only supports rectangle and path shapes!")


@dataclass
class PlaceBoundary(SpecctraField):
    LISP_SCHEMA = ["{rect|path}"]
    SCHEMA = Schema(
        [Field("rectangle", Rectangle, raw_name="rect"), Field("path", Path),]
    )
    rectangle: Optional[Rectangle] = None
    path: Optional[Path] = None

    @property
    def shape(self) -> Union[Path, Rectangle]:
        shape = self.rectangle or self.path
        if not shape:
            raise RuntimeError(f"{self} is missing a shape!")
        return shape

    @shape.setter
    def shape(self, new_shape: Union[Path, Rectangle]) -> None:
        if isinstance(new_shape, Rectangle):
            self.rectangle = new_shape
        elif isinstance(new_shape, Path):
            self.path = new_shape
        else:
            raise RuntimeError("PlaceBoundary only supports rectangle and path shapes!")


@dataclass
class Via(SpecctraField):
    LISP_SCHEMA = ["[padstack_ids]"]
    SCHEMA = Schema([ListField("padstack_ids", str),])

    # I have no idea what this class does, it seems to have something to do with
    # specifying which vias are ok to use for routing?
    padstack_ids: List[str]

    # spare


@dataclass
class Structure(SpecctraField):
    LISP_SCHEMA = [
        "[{layer}]",
        "[{boundary}]",
        "?{place_boundary}",
        "?[{plane}]",
        "{via}",
        "{rule}",
    ]
    SCHEMA = Schema(
        [
            ListField("layers", Layer, raw_name="layer"),
            ListField("boundaries", Boundary, raw_name="boundary"),
            Field("place_boundary", PlaceBoundary),
            ListField("planes", Plane, raw_name="plane"),
            Field("via", Via),
            Field("rules", Rules, raw_name="rule"),
        ]
    )

    layers: List[Layer]
    boundaries: List[Boundary]
    place_boundary: Optional[Union[Path, Rectangle]]
    planes: List[Plane]
    via: Via

    # Note that rules are serialized a bit weirdly, with one rule statement
    # and then a list of actual rules
    # Also note there are a _LOT_ more rule types to be implemented.
    # rules: List[Union[WidthRule, ClearanceRule]]
    rules: Rules

    # unit or resolution or null
    # layer_noise_weight_descriptor optional
    # [region] optional
    # [keepout] optional
    # control optional
    # structure place rule optional
    # [grid]

    # MISSING RULE TYPES:
    #  <effective_via_length_descriptor>
    #  <interlayer_clearance_descriptor>
    #  <junction_type_descriptor>
    #  <length_amplitude_descriptor>
    #  <length_factor_descriptor>
    #  <length_gap_descriptor>
    #  <limit_bends_descriptor>
    #  <limit_crossing_descriptor>
    #  <limit_vias_descriptor>
    #  <limit_way_descriptor>
    #  <max_noise_descriptor>
    #  <max_stagger_descriptor>
    #  <max_stub_descriptor>
    #  <max_total_vias_descriptor>
    #  {<parallel_noise_descriptor>}
    #  {<parallel_segment_descriptor>}
    #  <pin_width_taper_descriptor>
    #  <power_fanout_descriptor>
    #  <redundant_wiring_descriptor>
    #  <reorder_descriptor>
    #  <restricted_layer_length_factor_descriptor>
    #  <saturation_length_descriptor>
    #  <shield_gap_descriptor>
    #  <shield_loop_descriptor>
    #  <shield_tie_down_interval_descriptor>
    #  <shield_width_descriptor>
    #  {<stack_via_descriptor>}
    #  {<stack_via_depth_descriptor>}
    #  {<tandem_noise_descriptor>}
    #  {<tandem_segment_descriptor>}
    #  <tandem_shield_overhang_descriptor>
    #  <testpoint_rule_descriptor>
    #  <time_length_factor_descriptor>
    #  <tjunction_descriptor>
    #  <track_id_descriptor>
    #  <via_at_smd_descriptor>
    #  <via_pattern_descriptor>


@dataclass
class Parser(SpecctraField):
    LISP_SCHEMA = [
        "?{string_quote}",
        "?{space_in_quoted_tokens}",
        "?{host_cad}",
        "?{host_version}",
    ]
    SCHEMA = Schema(
        [
            Field("string_quote", str),
            Field("space_in_quoted_tokens", _parse_specctra_bool),
            Field("host_cad", str),
            Field("host_version", str),
        ]
    )
    string_quote: str = ""
    space_in_quoted_tokens: bool = False
    host_cad: str = ""
    host_version: str = ""

    # [constants??]
    # write resolution
    # routes include
    # wires include
    # case_sensitive
    # via_rotate_first


@dataclass
class PCB(SpecctraField):
    LISP_SCHEMA = [
        "name",
        "?{parser}",
        "?{resolution}",
        "?{unit}",
        "{structure}",
        "{placement}",
        "{library}",
        "{network}",
        "{wiring}",
    ]
    SCHEMA = Schema(
        [
            Field("name", str),
            Field("parser", Parser),
            Field("resolution", Quantity),
            Field("unit", str),
            Field("structure", Structure),
            Field("placement", Placement),
            Field("library", Library),
            Field("network", Network),
            Field("wiring", Wiring),
        ]
    )

    name: str
    parser: Parser
    resolution: Quantity
    unit: str
    structure: Structure
    placement: Placement
    library: Library
    network: Network
    wiring: Optional[Wiring] = None

    # capacitance resolution optional
    # conductance resolution optional
    # current resolution optional
    # inductance resolution optional
    # resistance resolution optional
    # time_resolution optional
    # voltage_resolution optional
    # floor_plan(or file)
    #    unit optional
    #     resolution optional
    #     [cluster] optional
    #     [room] optional
    # part_library(or file)
    #    [physical_part_mapping] optional
    #     [logical_part_mappings]
    #     [logical_part] optional
    #     directory optional
    # colors optional
    # - the spec says the colours are not optional
    # - but my example files don't use it.
    #     [color]
    #         number
    #         name
    #         r
    #         g
    #         b
    #     [set_color]
    #         color_object
    #         name
    #     [set_pattern]
    #         pattern_object
    #         pattern_name


@dataclass
class RoutedNet(SpecctraField):
    LISP_SCHEMA = ["net_id", "[{wire}]"]
    SCHEMA = Schema([Field("net_id", str), ListField("wires", Wire, raw_name="wire"),])

    net_id: str
    wires: List[Wire]


@dataclass
class RoutedNetwork(SpecctraField):
    LISP_SCHEMA = ["[{net}]"]
    SCHEMA = Schema([ListField("nets", RoutedNet, raw_name="net"),])

    nets: List[RoutedNet]


@dataclass
class Routes(SpecctraField):
    LISP_SCHEMA = ["?{resolution}", "{parser}", "{library_out}", "{network_out}"]
    SCHEMA = Schema(
        [
            Field("resolution", Quantity),
            Field("parser", Parser),
            Field("library", Library, raw_name="library_out"),
            Field("network", RoutedNetwork, raw_name="network_out"),
        ]
    )

    resolution: Quantity
    parser: Parser
    library: Library
    network: RoutedNetwork


@dataclass
class Session(SpecctraField):
    LISP_SCHEMA = ["name", "?{base_design}", "{placement}", "{was_is}", "{routes}"]
    SCHEMA = Schema(
        [
            Field("name", str),
            IgnoreField("base_design"),
            Field("placement", Placement),
            IgnoreField("was_is"),
            Field("routes", Routes),
        ]
    )

    name: str
    placement: Placement
    routes: Routes


@dataclass
class Specctra(SpecctraField):
    LISP_SCHEMA = ["{pcb}"]
    SCHEMA = Schema([Field("pcb", PCB),])

    pcb: PCB

    @classmethod
    def get_quote_string(self, dsn_dict: Dict[str, Any]) -> str:
        return str(dsn_dict["pcb"]["parser"].get("string_quote", '"'))


@dataclass
class SpecctraSession(SpecctraField):
    """Parent container for specctra session (SES) files."""

    LISP_SCHEMA = ["{session}"]
    SCHEMA = Schema([Field("session", Session),])

    session: Session

    @classmethod
    def get_quote_string(self, dsn_dict: Dict[str, Any]) -> str:
        return str(dsn_dict["session"]["routes"]["parser"].get("string_quote", '"'))
