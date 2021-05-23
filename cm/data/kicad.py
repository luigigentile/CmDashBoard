"""KiCad data models."""
import itertools
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Sequence, Union, cast

from cm.data import vector
from cm.data.lisp import LispSerializable
from cm.data.schema import Field, IgnoreField, ListField, Schema

Shape = Union["Text", "Line", "Circle", "Arc", "Polygon"]


def _parse_hex_datetime(hex_value: str) -> datetime:
    return datetime.fromtimestamp(int(hex_value, 16))


def _parse_vertex_2d(raw_vertex: Dict[str, str]) -> "Vertex2D":
    """Parse a kicad vertex into a vertex object."""
    return Vertex2D(float(raw_vertex.get("x", 0)), float(raw_vertex.get("y", 0)),)


def _parse_vertex_3d(x: str = "0", y: str = "0", z: str = "0") -> "Vertex3D":
    """Parse a kicad 3d vertex into a Vertex3D object."""
    return Vertex3D(float(x), float(y), float(z))


def _parse_layer(values: Dict[str, Any]) -> "Layer":
    """Layers in kicad aren't valid lisp, so we parse them manually."""
    return Layer(
        index=int(values["index"]),
        name=values["name"],
        layer_type=LayerType(values["type"]),
    )


class TextType(Enum):
    REFERENCE = "reference"
    VALUE = "value"
    USER = "user"


class PadType(Enum):
    THRU_HOLE = "thru_hole"
    SMD = "smd"
    # CONNECT = 'connect'  # Not supported yet
    NP_THRU_HOLE = "np_thru_hole"


class PadShape(Enum):
    CIRCLE = "circle"
    RECT = "rect"
    ROUNDRECT = "roundrect"  # FIXME: this needs a serializer / exporter?
    # OVAL = 'oval'  # Not supported yet
    # TRAPEZOID = 'trapezoid'  # Not supported yet


class ZoneConnect(Enum):
    NOT_COVERED = 0
    THERMAL_RELIEF = 1
    SOLID = 2
    THERMAL_RELIEF_THRU_HOLE = 3


class LayerType(Enum):
    SIGNAL = "signal"
    USER = "user"
    POWER = "power"
    MIXED = "mixed"
    JUMPER = "jumper"


class KiCadField(LispSerializable):
    """Abstract base class for all Specctra fields, for easy type matching"""

    @classmethod
    def get_serializer(cls, value: Any) -> Callable[[Any], Any]:
        # We overwrite the standard serializer to allow for some format-specific serializers.

        if isinstance(value, datetime):
            # Format floats as hex-encoded unix timestamps.
            return lambda x: "{:X}".format(int(x.timestamp()))

        return super().get_serializer(value)


@dataclass(eq=False)
class Vertex2D(vector.Vector, KiCadField):
    """Subclass of Vector, for lisp-serializable 2D Vertices."""

    LISP_SCHEMA = ["x", "y"]
    SCHEMA = Schema(
        [
            Field("x", float, serialize_default=True, default=0),
            Field("y", float, serialize_default=True, default=0),
        ]
    )

    x: float = 0
    y: float = 0
    z: float = 0  # Needed only to make the constructor compatible with the parent class


@dataclass(eq=False)
class Vertex3D(vector.Vector, KiCadField):
    """Subclass of Vector, for lisp-serializable 3D Vertices."""

    LISP_SCHEMA = ["x", "y", "z"]
    SCHEMA = Schema(
        [
            Field("x", float, serialize_default=True, default=0),
            Field("y", float, serialize_default=True, default=0),
            Field("z", float, serialize_default=True, default=0),
        ]
    )

    x: float = 0
    y: float = 0
    z: float = 0


@dataclass
class FontSize(KiCadField):
    LISP_SCHEMA = ["width", "height"]
    SCHEMA = Schema([Field("width", float), Field("height", float),])
    width: float
    height: float


@dataclass
class Font(KiCadField):
    LISP_SCHEMA = ["{size}", "{thickness}"]
    SCHEMA = Schema(
        [Field("size", FontSize), Field("line_width", float, raw_name="thickness"),]
    )
    size: FontSize
    line_width: float


@dataclass
class TextEffects(KiCadField):
    LISP_SCHEMA = ["{font}"]
    SCHEMA = Schema([Field("font", Font),])
    font: Font


@dataclass
class Placement(KiCadField):
    LISP_SCHEMA = ["[2]position", "?angle"]
    SCHEMA = Schema([Field("position", _parse_vertex_2d), Field("angle", float),])
    position: Vertex2D
    angle: float = 0


@dataclass
class Text(KiCadField):
    LISP_SCHEMA = ["text_type", "text", "{at}", "{layer}", "?hide", "{effects}"]
    SCHEMA = Schema(
        [
            Field("text_type", TextType),
            Field("text", str),
            Field("placement", Placement, raw_name="at"),
            Field("layer", str),
            Field("hide", bool),
            Field("effects", TextEffects),
        ]
    )
    text_type: TextType
    text: str
    placement: Placement
    effects: TextEffects
    layer: str
    hide: bool = False


@dataclass
class Line(KiCadField):
    LISP_SCHEMA = ["{start}", "{end}", "{layer}", "{width}"]
    SCHEMA = Schema(
        [
            Field("start", _parse_vertex_2d),
            Field("end", _parse_vertex_2d),
            Field("layer", str),
            Field("line_width", float, raw_name="width"),
        ]
    )
    start: Vertex2D
    end: Vertex2D
    layer: str
    line_width: float


@dataclass
class Circle(KiCadField):
    LISP_SCHEMA = ["{center}", "{end}", "{layer}", "{width}"]
    SCHEMA = Schema(
        [
            Field("center", _parse_vertex_2d),
            Field("end", _parse_vertex_2d),
            Field("layer", str),
            Field("line_width", float, raw_name="width"),
        ]
    )
    center: Vertex2D
    end: Vertex2D
    layer: str
    line_width: float


@dataclass
class Arc(KiCadField):
    LISP_SCHEMA = ["{start}", "{end}", "?{angle}", "{layer}", "{width}"]
    SCHEMA = Schema(
        [
            Field("start", _parse_vertex_2d),
            Field("end", _parse_vertex_2d),
            Field("angle", float),
            Field("layer", str),
            Field("line_width", float, raw_name="width"),
        ]
    )
    start: Vertex2D
    end: Vertex2D
    layer: str
    line_width: float
    angle: float = 0


@dataclass
class Points(KiCadField):
    LISP_SCHEMA = ["[{xy}]"]
    SCHEMA = Schema([ListField("vertices", _parse_vertex_2d, raw_name="xy"),])
    vertices: List[Vertex2D]


@dataclass
class Polygon(KiCadField):
    LISP_SCHEMA = ["{pts}", "{layer}", "{width}"]
    SCHEMA = Schema(
        [
            Field("points", Points, raw_name="pts"),
            Field("layer", str),
            Field("line_width", float, raw_name="width"),
        ]
    )
    points: Points
    layer: str
    line_width: float


@dataclass
class RectDelta(KiCadField):
    LISP_SCHEMA = ["dx", "dy"]
    SCHEMA = Schema([Field("dx", float), Field("dy", float),])
    dx: float
    dy: float


class Drill(KiCadField):
    pass


@dataclass
class RoundDrill(Drill):
    LISP_SCHEMA = ["size", "?{offset}"]
    SCHEMA = Schema([Field("size", float), Field("offset", _parse_vertex_2d),])
    size: float
    offset: Vertex2D = Vertex2D()


@dataclass
class OvalDrill(Drill):
    LISP_SCHEMA = ["oval", "width", "height", "?{offset}"]
    SCHEMA = Schema(
        [
            IgnoreField("oval"),
            Field("width", float),
            Field("height", float),
            Field("offset", _parse_vertex_2d),
        ]
    )
    width: float
    height: float
    offset: Vertex2D = Vertex2D()


@dataclass
class Net(KiCadField):
    LISP_SCHEMA = ["number", "name"]
    SCHEMA = Schema([Field("number", int), Field("name", str),])
    number: int
    name: str


@dataclass
class PadSize(KiCadField):
    LISP_SCHEMA = ["width", "height"]
    SCHEMA = Schema([Field("width", float), Field("height", float),])

    width: float
    height: float


@dataclass
class Pad(KiCadField):
    LISP_SCHEMA = [
        "name",
        "type",
        "shape",
        "{at}",
        "{size}",
        "?{rect_delta}",
        "?{drill oval|drill}",
        "{layers}",
        "?{roundrect_rratio}",
        "?{net}",
        "?{die_length}",
        "?{solder_mask_margin}",
        "?{clearance}",
        "?{solder_paste_margin}",
        "?{solder_paste_margin_ratio}",
        "?{zone_connect}",
        "?{thermal_width}",
        "?{thermal_gap}",
    ]
    SCHEMA = Schema(
        [
            Field("name", str),
            Field("pad_type", PadType, raw_name="type"),
            Field("pad_shape", PadShape, raw_name="shape"),
            Field("placement", Placement, raw_name="at"),
            Field("size", PadSize),
            ListField("layers", str),
            Field("roundrect_ratio", float, raw_name="roundrect_rratio"),  # not a typo!
            Field("rect_delta", RectDelta),
            Field("drill_round", RoundDrill, raw_name="drill"),
            Field("drill_oval", OvalDrill, raw_name="drill oval"),
            Field("net", Net),
            Field("die_length", float),
            Field("solder_mask_margin", float),
            Field("clearance", float),
            Field("solder_paste_margin", float),
            Field("solder_paste_margin_ratio", float),
            Field("zone_connect", ZoneConnect),
            Field("thermal_width", float),
            Field("thermal_gap", float),
        ]
    )

    name: str
    pad_type: PadType
    pad_shape: PadShape
    placement: Placement
    size: PadSize
    layers: List[str]
    roundrect_ratio: float = 1
    rect_delta: Optional[RectDelta] = None
    drill_round: Optional[RoundDrill] = None
    drill_oval: Optional[OvalDrill] = None
    net: Optional[Net] = None
    die_length: Optional[float] = None
    solder_mask_margin: Optional[float] = None
    clearance: Optional[float] = None
    solder_paste_margin: Optional[float] = None
    solder_paste_margin_ratio: Optional[float] = None
    zone_connect: Optional[ZoneConnect] = None
    thermal_width: Optional[float] = None
    thermal_gap: Optional[float] = None

    @property
    def drill(self) -> Drill:
        # Exactly one of drill or drill_oval is always given
        drill = self.drill_round or self.drill_oval
        if not drill:
            raise RuntimeError(f"{self} is missing a drill attribute!")
        return drill

    @drill.setter
    def drill(self, new_drill: Drill) -> None:
        if isinstance(new_drill, OvalDrill):
            self.drill_oval = new_drill
        elif isinstance(new_drill, RoundDrill):
            self.drill_round = new_drill


@dataclass
class XYZ(KiCadField):
    """Annoying placeholder container to deal with the fact that 3d coordinates are encoded in multiple levels."""

    LISP_SCHEMA = ["{xyz}"]
    SCHEMA = Schema([Field("vertex", Vertex3D, raw_name="xyz"),])

    vertex: Vertex3D


@dataclass
class Model3D(KiCadField):
    LISP_SCHEMA = ["path", "{at}", "{scale}", "{rotate}"]
    SCHEMA = Schema(
        [
            Field("path", str),
            Field("position", XYZ, raw_name="at"),
            Field("scale", XYZ),
            Field("rotate", XYZ),
        ]
    )
    path: str
    position: XYZ
    scale: XYZ
    rotate: XYZ


@dataclass
class Module(KiCadField):
    LISP_SCHEMA = [
        "name",
        "{layer}",
        "?{tedit}",
        "?{tstamp}",
        "?{at}",
        "?{descr}",
        "?{tags}",
        "?{path}",
        "?{attr}",
        "[{fp_text|fp_line|fp_circle|fp_arc|fp_poly}]",
        "[{pad}]",
        "?{model}",
    ]
    SCHEMA = Schema(
        [
            Field("name", str),
            Field("layer", str),
            Field("edit_timestamp", _parse_hex_datetime, raw_name="tedit"),
            Field("timestamp", _parse_hex_datetime, raw_name="tstamp"),
            Field("placement", Placement, raw_name="at"),
            Field("description", str, raw_name="descr"),
            ListField(
                "tags",
                str,
                # Tags are given as a comma-separated string, this needs to be split into a list before deserialization,
                # and back into a list before serialization.
                # FIXME: there is some weird behavior here. Because kicad uses a lisp format,
                # preprocessing a string into a list causes some issues, because lisp_to_dict only knows that
                # the field is a list field, not that it's a list field that expects a string.
                # Because of that, it returns the value as a list with a single string, instead of just a string.
                preprocess=lambda v: cast(List[str], v)[0].split(" "),
                postprocess=lambda v: [" ".join(v)],
            ),
            Field("path", str),
            Field("attr", str),
            ListField("texts", Text, raw_name="fp_text"),
            ListField("lines", Line, raw_name="fp_line"),
            ListField("circles", Circle, raw_name="fp_circle"),
            ListField("arcs", Arc, raw_name="fp_arc"),
            ListField("polygons", Polygon, raw_name="fp_poly"),
            ListField("pads", Pad, raw_name="pad"),
            Field("model", Model3D),
        ]
    )

    name: str
    layer: str
    edit_timestamp: Optional[datetime] = None
    timestamp: Optional[datetime] = None
    placement: Placement = Placement(Vertex2D(), 0)
    description: str = ""
    path: str = ""
    attr: str = ""
    tags: List[str] = field(default_factory=list)

    # Shapes - these are usually accessed with the shapes property as one.
    texts: List[Text] = field(default_factory=list)
    lines: List[Line] = field(default_factory=list)
    circles: List[Circle] = field(default_factory=list)
    arcs: List[Arc] = field(default_factory=list)
    polygons: List[Polygon] = field(default_factory=list)

    pads: List[Pad] = field(default_factory=list)
    model: Optional[Model3D] = None

    @property
    def shapes(self) -> Sequence[Shape]:
        return list(
            itertools.chain(
                self.texts, self.lines, self.circles, self.arcs, self.polygons
            )
        )

    @shapes.setter
    def shapes(self, new_shapes: List[Shape]) -> None:
        self.texts = [s for s in new_shapes if isinstance(s, Text)]
        self.lines = [s for s in new_shapes if isinstance(s, Line)]
        self.circles = [s for s in new_shapes if isinstance(s, Circle)]
        self.arcs = [s for s in new_shapes if isinstance(s, Arc)]
        self.polygons = [s for s in new_shapes if isinstance(s, Polygon)]


@dataclass
class KiCadMod(KiCadField):
    """The outer wrapper in a KiCad mod file."""

    LISP_SCHEMA = ["{module}"]
    SCHEMA = Schema([Field("module", Module),])
    module: Module


@dataclass
class Layer(KiCadField):
    LISP_SCHEMA = ["index", "name", "type"]
    SCHEMA = Schema(
        [
            Field("index", int),
            Field("name", str),
            Field("layer_type", LayerType, raw_name="type"),
        ]
    )
    index: int
    name: str
    layer_type: LayerType

    @classmethod
    def dict_to_lisp(cls, data: Dict[str, Any], quote_string: str = "") -> List[Any]:
        # We need to overwrite this method because the layer schema isn't valid lisp.
        # It's formatted as (index name layer_type), not (*layer* index name layer_type)
        return [
            [data["index"], cls._quote_string(data["name"], quote_string), data["type"]]
        ]


@dataclass
class Layers(KiCadField):
    LISP_SCHEMA = ["[layer]"]
    SCHEMA = Schema([ListField("layers", _parse_layer, raw_name="layer")])
    layers: List[Layer]


@dataclass
class NetClass(KiCadField):
    LISP_SCHEMA = [
        "name",
        "description",
        "{clearance}",
        "{trace_width}",
        "{via_dia}",
        "{via_drill}",
        "{uvia_dia}",
        "{uvia_drill}",
        "?[{add_net}]",
    ]
    SCHEMA = Schema(
        [
            Field("name", str),
            Field("description", str),
            Field("clearance", float),
            Field("trace_width", float),
            Field("via_dia", float),
            Field("via_drill", float),
            Field("uvia_dia", float),
            Field("uvia_drill", float),
            ListField("nets", str, raw_name="add_net"),
        ]
    )

    name: str
    description: str
    clearance: float
    trace_width: float
    via_dia: float
    via_drill: float
    uvia_dia: float
    uvia_drill: float
    nets: List[str]


@dataclass
class Segment(KiCadField):
    LISP_SCHEMA = ["{start}", "{end}", "?{width}", "{layer}", "{net}"]
    SCHEMA = Schema(
        [
            Field("start", Vertex2D),
            Field("end", Vertex2D),
            Field("width", float),
            Field("layer", str),
            Field("net_id", int, raw_name="net"),
        ]
    )

    start: Vertex2D
    end: Vertex2D
    layer: str
    net_id: int
    width: float = 0


@dataclass
class Via(KiCadField):
    LISP_SCHEMA = ["{at}", "{size}", "{drill}", "{layers}", "{net}"]
    SCHEMA = Schema(
        [
            Field("position", Vertex2D, raw_name="at"),
            Field("size", float),
            Field("drill", float),
            ListField("layers", str),
            Field("net_id", int, raw_name="net"),
        ]
    )

    position: Vertex2D
    size: float
    drill: float
    layers: List[str]
    net_id: int


@dataclass
class Host(KiCadField):
    LISP_SCHEMA = ["app_name", "version"]
    SCHEMA = Schema([Field("app_name", str), Field("version", str)])

    app_name: str
    version: str


@dataclass
class PCB(KiCadField):
    LISP_SCHEMA = [
        "{version}",
        "{host}",
        "?{general}",
        "?{page}",
        "{layers}",
        "?{setup}",
        "[{net}]",
        "?[{net_class}]",
        "[{module}]",
        "?[{gr_text|gr_line|gr_arc|gr_circle|gr_polygon}]",
        "?[{segment|via}]",
    ]
    SCHEMA = Schema(
        [
            Field("version", str),
            Field("host", Host),
            IgnoreField("general"),
            IgnoreField("page"),
            Field("layers", Layers),
            IgnoreField("setup"),
            ListField("nets", Net, raw_name="net"),
            ListField("net_classes", NetClass, raw_name="net_class"),
            ListField("modules", Module, raw_name="module"),
            ListField("texts", Text, raw_name="gr_text"),
            ListField("lines", Line, raw_name="gr_line"),
            ListField("circles", Circle, raw_name="gr_circle"),
            ListField("arcs", Arc, raw_name="gr_arc"),
            ListField("polygons", Polygon, raw_name="gr_poly"),
            ListField("segments", Segment, raw_name="segment"),
            ListField("vias", Via, raw_name="via"),
        ]
    )

    layers: Layers
    nets: List[Net]
    net_classes: List[NetClass]
    modules: List[Module]
    segments: List[Segment]
    vias: List[Via]
    host: Host
    # Shapes - these are usually accessed with the shapes property as one.
    texts: List[Text] = field(default_factory=list)
    lines: List[Line] = field(default_factory=list)
    circles: List[Circle] = field(default_factory=list)
    arcs: List[Arc] = field(default_factory=list)
    polygons: List[Polygon] = field(default_factory=list)
    version: str = ""

    @property
    def shapes(self) -> Sequence[Shape]:
        return list(
            itertools.chain(
                self.texts, self.lines, self.circles, self.arcs, self.polygons
            )
        )

    @shapes.setter
    def shapes(self, new_shapes: List[Shape]) -> None:
        self.texts = [s for s in new_shapes if isinstance(s, Text)]
        self.lines = [s for s in new_shapes if isinstance(s, Line)]
        self.circles = [s for s in new_shapes if isinstance(s, Circle)]
        self.arcs = [s for s in new_shapes if isinstance(s, Arc)]
        self.polygons = [s for s in new_shapes if isinstance(s, Polygon)]


@dataclass
class KiCadPCB(KiCadField):
    """The outer wrapper in a KiCad PCB file."""

    LISP_SCHEMA = ["{kicad_pcb}"]
    SCHEMA = Schema([Field("pcb", PCB, raw_name="kicad_pcb"),])
    pcb: PCB
