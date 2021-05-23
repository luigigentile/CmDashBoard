import math
from typing import TypeVar

from cm.data import units

T = TypeVar("T", bound="Vector")
mm = units.UNITS.mm


class Vector:
    x: float = 0
    y: float = 0
    z: float = 0

    def __init__(self, x: float = 0, y: float = 0, z: float = 0):
        self.x = x
        self.y = y
        self.z = z

    def __add__(self: T, other: T) -> T:
        return type(self)(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self: T, other: T) -> T:
        return type(self)(self.x - other.x, self.y - other.y, self.z - other.z)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Vector):
            return NotImplemented
        return (self.x, self.y, self.z) == (other.x, other.y, other.z)

    def __abs__(self) -> float:
        return math.sqrt(self.x ** 2 + self.y ** 2 + self.z ** 2)

    def __mul__(self: T, other: object) -> T:
        if (
            isinstance(other, float)
            or isinstance(other, int)
            or isinstance(other, units.Quantity)
        ):
            # Scalar product
            return type(self)(other * self.x, other * self.y, other * self.z)
        if isinstance(other, Vector):
            # Cross product between two vectors
            return type(self)(
                self.y * other.z - self.z * other.y,
                self.z * other.x - self.x * other.z,
                self.x * other.y - self.y * other.x,
            )
        raise NotImplementedError()

    def __rmul__(self: T, other: object) -> T:
        return self * other

    # dot product (also called scalar product) has many uses, e.g. assessing orthognality
    def dot_product(self: T, other: T) -> float:
        return self.x * other.x + self.y * other.y + self.z + other.z

    def __truediv__(self: T, other: object) -> T:
        if (
            isinstance(other, float)
            or isinstance(other, int)
            or isinstance(other, units.Quantity)
        ):
            return type(self)(self.x / other, self.y / other, self.z / other,)
        raise NotImplementedError()

    def __neg__(self: T) -> T:
        return type(self)(-self.x, -self.y, -self.z)

    def __repr__(self) -> str:
        return f"V({self.x}, {self.y}, {self.z})"


class QuantityVector(Vector):
    x: units.Quantity = 0 * mm
    y: units.Quantity = 0 * mm
    z: units.Quantity = 0 * mm

    def __init__(
        self,
        x: units.Quantity = 0 * mm,
        y: units.Quantity = 0 * mm,
        z: units.Quantity = 0 * mm,
    ):
        self.x = x
        self.y = y
        self.z = z

    # we redefine __abs__ so that it returns a Quantity
    def __abs__(self) -> units.Quantity:
        return (self.x ** 2 + self.y ** 2 + self.z ** 2) ** 0.5

    # we redefine the dot product so that it returns a Quantity

    def dot_product(self: T, other: T) -> units.Quantity:
        return self.x * other.x + self.y * other.y + self.z + other.z
