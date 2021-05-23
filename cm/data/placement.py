from dataclasses import dataclass

from cm.data import schemas, serializable
from cm.data.units import UNITS, Quantity

deg = UNITS("deg")
mm = UNITS("mm")


@dataclass
class Placement(serializable.Serializable):
    SCHEMA = schemas.PLACEMENT_SCHEMA
    x: Quantity = 0 * mm
    y: Quantity = 0 * mm
    rotation: Quantity = 0 * deg
