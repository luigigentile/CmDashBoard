import math
from dataclasses import dataclass, field
from typing import List, TypeVar

from cm.data import serializable, units, vector
from cm.data.schema import Field, ListField, Schema

deg = units.UNITS("deg")
rad = units.UNITS("rad")
mm = units.UNITS("mm")

origin = vector.QuantityVector()

T = TypeVar("T", bound="Shape")


@dataclass
class Shape(serializable.Serializable):
    """Abstract base class for all shapes."""

    SCHEMA = Schema(
        [
            Field("rotation", units.parser(units.ANGLE)),
            Field("line_width", units.parser(units.LENGTH)),
            Field("is_filled", bool),
        ]
    )

    rotation: units.Quantity = 0 * deg
    line_width: units.Quantity = 0 * mm
    is_filled: bool = False

    def is_congruent(self: T, other: "Shape") -> bool:
        """Check if two shapes are congruent (equal in shape and size)."""
        raise NotImplementedError()

    def centroid(self) -> vector.QuantityVector:
        """Return the geometric center of the shape."""
        raise NotImplementedError()

    def at_origin(self: T) -> T:
        """Return a copy of this shape with its centroid moved to the origin."""
        raise NotImplementedError()

    @property
    def width(self) -> units.Quantity:
        """Width of the shape. For some shapes the width is arbitrary, as it depends on the orientation."""
        raise NotImplementedError()

    @property
    def height(self) -> units.Quantity:
        """Height of the shape. For some shapes the height is arbitrary, as it depends on the orientation."""
        raise NotImplementedError()


@dataclass
class Line(Shape):
    """Single line segment.

    Line segments can be wires, if used on copper layers.
    """

    SCHEMA = Schema(
        [
            Field("rotation", units.parser(units.ANGLE)),
            Field("line_width", units.parser(units.LENGTH)),
            Field("is_filled", bool),
            Field("start", vector.QuantityVector),
            Field("end", vector.QuantityVector),
        ]
    )

    start: vector.QuantityVector = origin
    end: vector.QuantityVector = origin

    def is_congruent(self: "Line", other: "Shape") -> bool:
        if not isinstance(other, Line):
            return False
        # Two lines are congruent if the difference of their start and end vectors is the same,
        # or if they are exactly opposite.
        # I.e. they have the same angle and magnitude, even if the direction is flipped.
        diff_self = self.end - self.start
        diff_other = other.end - other.start
        return diff_self == diff_other or diff_self == -diff_other

    def centroid(self) -> vector.QuantityVector:
        # The center of a line is at the average of the start and end vector
        return (self.start + self.end) / 2

    def at_origin(self) -> "Line":
        centroid = self.centroid()
        return Line(start=self.start - centroid, end=self.end - centroid)

    @property
    def width(self) -> units.Quantity:
        # We arbitrarily decide to make the width the length of the line, and the height 0.
        return abs(self.end - self.start)

    @property
    def height(self) -> units.Quantity:
        # We arbitrarily decide to make the width the length of the line, and the height 0.
        return 0 * mm


@dataclass
class Path(Shape):
    """A path made up of segments. Cannot cross layer boundaries"""

    SCHEMA = Schema(
        [
            Field("rotation", units.parser(units.ANGLE)),
            Field("line_width", units.parser(units.LENGTH)),
            Field("is_filled", bool),
            ListField("vertices", vector.QuantityVector),
        ]
    )

    vertices: List[vector.QuantityVector] = field(default_factory=list)

    def is_congruent(self: "Path", other: "Shape") -> bool:
        if not isinstance(other, Path):
            return False
        # Two paths are congruent if the difference of each of their segments is the same.
        # I.e. each segment has the same angle and magnitude
        if len(self.vertices) != len(other.vertices):
            return False
        if not self.vertices:
            return True
        self_last_vertex = self.vertices[0]
        other_last_vertex = other.vertices[0]
        for self_vertex, other_vertex in zip(self.vertices[1:], other.vertices[1:]):
            # Compare each segment - if one doesn't match, the shape isn't congruent
            # FIXME: Note this is quite naive, two paths can be the same even if their segments
            #        differ, as one segment in one can be made up of multiple smaller ones in the other.
            if not Line(self_last_vertex, self_vertex).is_congruent(
                Line(other_last_vertex, other_vertex)
            ):
                return False
        # Every segment is congruent, so the shape is congruent
        return True

    def centroid(self) -> vector.QuantityVector:
        # The center of a path is the average of all its vertices
        return sum(self.vertices, origin) / len(self.vertices)

    def at_origin(self) -> "Path":
        centroid = self.centroid()

        return Path(vertices=[v - centroid for v in self.vertices])

    @property
    def width(self) -> units.Quantity:
        # We arbitrarily pick a horizontal bounding box for the width / height
        x_coordinates = [v.x for v in self.vertices]
        # y_coordinates = [v.y for v in self.vertices]
        return max(x_coordinates) - min(x_coordinates)

    @property
    def height(self) -> units.Quantity:
        # We arbitrarily pick a horizontal bounding box for the width / height
        y_coordinates = [v.y for v in self.vertices]
        return max(y_coordinates) - min(y_coordinates)


@dataclass
class Polygon(Path):
    """A polygon is a path that is closed."""


@dataclass
class Rectangle(Shape):
    """A rectangle, either filled or not filled."""

    SCHEMA = Schema(
        [
            Field("rotation", units.parser(units.ANGLE)),
            Field("line_width", units.parser(units.LENGTH)),
            Field("is_filled", bool),
            Field("x1", units.parser(units.LENGTH)),
            Field("y1", units.parser(units.LENGTH)),
            Field("x2", units.parser(units.LENGTH)),
            Field("y2", units.parser(units.LENGTH)),
        ]
    )

    x1: units.Quantity = 0 * mm
    y1: units.Quantity = 0 * mm
    x2: units.Quantity = 0 * mm
    y2: units.Quantity = 0 * mm

    @property
    def width(self) -> units.Quantity:
        return abs(self.x2 - self.x1)

    @property
    def height(self) -> units.Quantity:
        return abs(self.y2 - self.y1)

    def is_congruent(self: "Rectangle", other: "Shape") -> bool:
        if not isinstance(other, Rectangle):
            return False
        # Two rectangles are congruent if they have the same width and height
        return bool(self.width == other.width and self.height == other.height)

    def centroid(self) -> vector.QuantityVector:
        return vector.QuantityVector(self.x1 + 0.5 * self.x2, self.y1 + 0.5 * self.y2)

    def at_origin(self) -> "Rectangle":
        centroid = self.centroid()
        return Rectangle(
            x1=self.x1 - centroid.x,
            y1=self.y1 - centroid.y,
            x2=self.x2 - centroid.x,
            y2=self.y2 - centroid.y,
        )


@dataclass
class Circle(Shape):
    SCHEMA = Schema(
        [
            Field("rotation", units.parser(units.ANGLE)),
            Field("line_width", units.parser(units.LENGTH)),
            Field("is_filled", bool),
            Field("center", vector.QuantityVector),
            Field("diameter", units.parser(units.LENGTH)),
        ]
    )

    center: vector.QuantityVector = origin
    diameter: units.Quantity = 0 * mm

    def is_congruent(self: "Circle", other: "Shape") -> bool:
        if not isinstance(other, Circle):
            return False
        # Two circles are congruent if they have the same diameter
        return bool(self.diameter == other.diameter)

    def centroid(self) -> vector.QuantityVector:
        return self.center

    def at_origin(self) -> "Circle":
        return Circle(center=origin, diameter=self.diameter)

    @property
    def width(self) -> units.Quantity:
        return self.diameter

    @property
    def height(self) -> units.Quantity:
        return self.diameter


@dataclass
class Text(Shape):
    """Text to be added on a layer."""

    SCHEMA = Schema(
        [
            Field("rotation", units.parser(units.ANGLE)),
            Field("line_width", units.parser(units.LENGTH)),
            Field("is_filled", bool),
            Field("position", vector.QuantityVector),
            Field("text", str),
            Field("font_size", int),
        ]
    )

    # TODO: This is incomplete, proper text support will require a lot more work.
    position: vector.QuantityVector = origin
    text: str = ""
    font_size: int = 1

    def is_congruent(self: "Text", other: "Shape") -> bool:
        if not isinstance(other, Text):
            return False
        # Two texts are congruent if they have the same size and text
        return self.text == other.text and self.font_size == other.font_size

    def centroid(self) -> vector.QuantityVector:
        return (
            self.position
        )  # TODO: This likely needs fixing depending on how we do alignment

    def at_origin(self) -> "Text":
        return Text(position=origin, text=self.text, font_size=self.font_size)


@dataclass
class Arc(Shape):
    SCHEMA = Schema(
        [
            Field("rotation", units.parser(units.ANGLE)),
            Field("line_width", units.parser(units.LENGTH)),
            Field("is_filled", bool),
            Field("center", vector.QuantityVector),
            Field("start", vector.QuantityVector),
            Field("angle", units.parser(units.ANGLE)),
        ]
    )

    center: vector.QuantityVector = origin
    start: vector.QuantityVector = origin
    angle: units.Quantity = 0 * deg

    @property
    def radius(self) -> units.Quantity:
        return abs(self.start - self.center)

    @property
    def end(self) -> vector.QuantityVector:
        """computes the end vector on the arc"""
        radius_vector = self.start - self.center
        rad_angle = self.angle.to("rad")

        rotated = vector.QuantityVector(
            x=radius_vector.x * math.cos(rad_angle)
            - radius_vector.y * math.sin(rad_angle),
            y=radius_vector.y * math.cos(rad_angle)
            + radius_vector.x * math.sin(rad_angle),
        )

        return self.center + rotated

    def is_congruent(self: "Arc", other: "Shape") -> bool:
        if not isinstance(other, Arc):
            return False
        # Two arcs are equal if they have the same radius and angle
        if self.angle != other.angle:
            return False

        self_radius = abs(self.start - self.center)
        other_radius = abs(other.start - other.center)

        return bool(self_radius == other_radius)

    def centroid(self) -> vector.QuantityVector:
        # See https://en.wikipedia.org/wiki/List_of_centroids
        radian_angle = self.angle * math.pi / (180 * deg)

        # First we need the direction of a vector going through the middle of the arc
        # center and start describe the side of the arc, so we need to add half the arc angle to it.
        side_vector = self.start - self.center
        radian_side_angle = math.atan2(
            side_vector.y.to(mm).magnitude, side_vector.x.to(mm).magnitude
        )
        radian_mid_angle = radian_side_angle + radian_angle / 2
        # Note this is a unit vector and should be dimensionless!
        mid_vector = vector.QuantityVector(
            x=math.cos(radian_mid_angle), y=math.sin(radian_mid_angle), z=0
        )
        radius = abs(side_vector)

        delta_x = (2 * radius * math.sin(radian_angle / 2)) / (1.5 * radian_angle)
        return self.center + mid_vector * delta_x  # type: ignore

    def at_origin(self) -> "Arc":
        centroid = self.centroid()
        return Arc(
            center=self.center - centroid, start=self.start - centroid, angle=self.angle
        )

    def as_path(self, resolution: units.Quantity) -> "Path":
        """Approximate an arc as a path."""
        # We use the radius vector (which is the same as the start vector for an arc around the origin)
        # as it's easiest to rotate vectors around the origin.
        radius_vector = self.start - self.center

        # compute how many vertices are needed for the approximation
        arc_length = (
            2 * math.pi * self.radius * abs(self.angle / 360 * deg)
        )  # circumference * (angle / 360 degrees)
        number_of_vertices = int(arc_length / resolution)
        number_of_vertices = max(number_of_vertices, 3)  # at least 3 points

        # construct the list of vertices
        approximated_vertices: List[vector.QuantityVector] = []
        number_of_segments = number_of_vertices - 1
        # We need to do some trigonometry, so all angles from here on out are in radians.
        angle_per_segment = (self.angle / number_of_segments).to(rad)
        rotation_angles = [
            angle_per_segment * (i + i) for i in range(number_of_segments)
        ]
        for rotation_angle in rotation_angles:
            # Calculate the rotated angle (note this works because radius_vector is relative to the origin)
            rotated = vector.QuantityVector(
                x=radius_vector.x * math.cos(rotation_angle)
                - radius_vector.y * math.sin(rotation_angle),
                y=radius_vector.y * math.cos(rotation_angle)
                + radius_vector.x * math.sin(rotation_angle),
            )
            # Move the vector back to the arc's actual position and add the vertex
            approximated_vertices.append(rotated + self.center)

        return Path(vertices=approximated_vertices, line_width=self.line_width)
