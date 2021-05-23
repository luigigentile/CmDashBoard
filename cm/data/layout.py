from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Tuple, Union

from cm.data import schemas, serializable, units, vector
from cm.data.shapes import Shape

LAYER = Union["ShapeLayer", "ViaLayer", "DrillLayer", "VertexLayer"]


@dataclass(eq=False)
class Vertex2D(serializable.Serializable, vector.QuantityVector):
    """Subclass for vector for serializing 2d vertices in layouts."""

    x: units.Quantity = 0 * units.UNITS("mm")
    y: units.Quantity = 0 * units.UNITS("mm")
    z: units.Quantity = 0 * units.UNITS(
        "mm"
    )  # Needed only to make the constructor compatible with the parent class

    SCHEMA = schemas.VERTEX2D_SCHEMA


class LayerType(Enum):
    SIGNAL = "signal"
    POWER = "power"
    MIXED = "mixed"


@dataclass
class Drill(serializable.Serializable):
    """Plated and unplated holes."""

    SCHEMA = schemas.DRILL_SCHEMA

    center: Vertex2D
    diameter: units.Quantity
    is_plated: bool


@dataclass
class Via(serializable.Serializable):
    """Plated hole, which can be restricted to certain layers."""

    SCHEMA = schemas.VIA_SCHEMA

    center: Vertex2D
    diameter: units.Quantity
    ring_diameter: units.Quantity  # Copper ring around drill
    from_layer: int  # Start layer of via
    to_layer: int  # End layer of via


@dataclass
class Pad(serializable.Serializable):
    """Thru-hole pad, with a drill through the entire board."""

    SCHEMA = schemas.PAD_SCHEMA

    name: str
    shape: Shape
    drill: Drill


@dataclass
class Layer(serializable.Serializable):
    """Parent class for all layer types."""

    layer_type: LayerType = LayerType.MIXED


@dataclass
class ShapeLayer(Layer):
    SCHEMA = schemas.SHAPE_LAYER_SCHEMA

    shapes: List[Shape] = field(default_factory=list)

    def __add__(self, other: "ShapeLayer") -> "ShapeLayer":
        return ShapeLayer(shapes=self.shapes + other.shapes)


@dataclass
class ViaLayer(Layer):
    SCHEMA = schemas.VIA_LAYER_SCHEMA

    vias: List[Via] = field(default_factory=list)

    def __add__(self, other: "ViaLayer") -> "ViaLayer":
        return ViaLayer(vias=self.vias + other.vias)


@dataclass
class DrillLayer(Layer):
    SCHEMA = schemas.DRILL_LAYER_SCHEMA

    drills: List[Drill] = field(default_factory=list)

    def __add__(self, other: "DrillLayer") -> "DrillLayer":
        return DrillLayer(drills=self.drills + other.drills)


@dataclass
class VertexLayer(Layer):
    SCHEMA = schemas.VERTEX_LAYER_SCHEMA

    vertices: List[Vertex2D] = field(default_factory=list)

    def __add__(self, other: "VertexLayer") -> "VertexLayer":
        return VertexLayer(vertices=self.vertices + other.vertices)


@dataclass
class PadLayer(Layer):
    SCHEMA = schemas.PAD_LAYER_SCHEMA

    pads: List[Pad] = field(default_factory=list)

    def __add__(self, other: "PadLayer") -> "PadLayer":
        return PadLayer(pads=self.pads + other.pads)


@dataclass(init=False)
class Layout(serializable.Serializable):
    """The physical layout of a Part or whole PCB.

    Layouts are composable. I.e. you can do

        board.layout += part.layout

    to add a part to a board's layout.
    """

    SCHEMA = schemas.LAYOUT_SCHEMA

    # Copper layers (0 is top, -1 is bottom)
    copper: List[ShapeLayer]

    # Global layers (affecting all copper layers)
    dimension: ShapeLayer  # Board outline
    pads: PadLayer  # Through-hole pads (through entire board)
    via: ViaLayer  # Positions of vias (layer information encoded in vias)
    drill: DrillLayer  # Plated and unplated drills
    mill: ShapeLayer  # Milling information

    # Top/bottom layers (affecting only the outer layers)
    smd: Tuple[ShapeLayer, ShapeLayer]  # SMD pads (top and bottom)
    silkscreen: Tuple[ShapeLayer, ShapeLayer]  # Silkscreen (top and bottom)
    mask: Tuple[ShapeLayer, ShapeLayer]  # Areas _without_ solder mask (top and bottom)
    paste: Tuple[ShapeLayer, ShapeLayer]  # Areas with solder paste (top and bottom)
    glue: Tuple[ShapeLayer, ShapeLayer]  # Areas with smd glue (top and bottom)
    test: Tuple[VertexLayer, VertexLayer]  # Test points (top and bottom)
    keepout: Tuple[
        ShapeLayer, ShapeLayer
    ]  # Keepout areas for restricting placement (top and bottom)
    documentation: Tuple[ShapeLayer, ShapeLayer]  # Fab Documentation
    internal_documentation: Tuple[
        ShapeLayer, ShapeLayer
    ]  # Internal-only documentation (not send to fab)

    def __init__(self, copper_layers: int):
        self.copper = [ShapeLayer() for x in range(copper_layers)]

        self.dimension = ShapeLayer()
        self.pads = PadLayer()
        self.via = ViaLayer()
        self.drill = DrillLayer()
        self.mill = ShapeLayer()

        self.smd = (ShapeLayer(), ShapeLayer())
        self.silkscreen = (ShapeLayer(), ShapeLayer())
        self.mask = (ShapeLayer(), ShapeLayer())
        self.paste = (ShapeLayer(), ShapeLayer())
        self.glue = (ShapeLayer(), ShapeLayer())
        self.test = (VertexLayer(), VertexLayer())
        self.keepout = (ShapeLayer(), ShapeLayer())

        self.documentation = (ShapeLayer(), ShapeLayer())
        self.internal_documentation = (ShapeLayer(), ShapeLayer())

    @property
    def pcb_layers(self) -> int:
        """Return the number of "real" pcb layers, i.e. copper layers."""
        return len(self.copper)

    @property
    def global_layers(
        self,
    ) -> Dict[str, Union[ShapeLayer, ViaLayer, DrillLayer, PadLayer]]:
        """Return a dictionary of all the global layers.

        Global layers are those layers that affect the entire stackup.
        """
        return {
            "dimension": self.dimension,
            "pads": self.pads,
            "via": self.via,
            "drill": self.drill,
            "mill": self.mill,
        }

    @property
    def outside_layers(
        self,
    ) -> Dict[
        str, Union[Tuple[ShapeLayer, ShapeLayer], Tuple[VertexLayer, VertexLayer]]
    ]:
        """Return a dictionary of all the outside layers.

        These are the layers that only apply on the outside of the board(top and bottom). """
        return {
            "silkscreen": self.silkscreen,
            "mask": self.mask,
            "paste": self.paste,
            "glue": self.glue,
            "test": self.test,
            "keepout": self.keepout,
        }

    def __add__(self, other: "Layout") -> "Layout":
        new_layout = Layout(copper_layers=self.pcb_layers)
        if not isinstance(other, Layout):
            raise TypeError(
                f"{other} is a {type(other)}, hence it cannot be added to the Layout {self}."
            )

        # Check if number of copper layers is compatible.
        # It might be possible to add a layout with fewer layers to a layout with more layers,
        # but for now we only allow equal numbers
        if other.pcb_layers != self.pcb_layers:
            raise ValueError(
                f"Cannot add layout with {other.pcb_layers} layers to a layout with {self.pcb_layers} layers."
            )

        # Add copper layers together
        for layer_index, (self_layer, other_layer) in enumerate(
            zip(self.copper, other.copper)
        ):
            new_layout.copper[layer_index] = self_layer + other_layer

        # add up all the global layers
        other_global_layers = other.global_layers
        for layer_name, layer in self.global_layers.items():
            setattr(
                new_layout,
                layer_name,
                layer + other_global_layers[layer_name],  # type: ignore
            )

        # Add up all the top/bottom layers
        other_outside_layers = other.outside_layers
        for layer_name, (top, bottom) in self.outside_layers.items():
            setattr(
                new_layout,
                layer_name,
                [
                    top + other_outside_layers[layer_name][0],  # type: ignore
                    bottom + other_outside_layers[layer_name][1],  # type: ignore
                ],
            )

        return new_layout
