from dataclasses import dataclass
from typing import List

from cm.data import schemas
from cm.data.net import Net
from cm.data.serializable import Serializable
from cm.data.vector import QuantityVector


@dataclass
class Trace(Serializable):
    """PCB trace - a connected shape of copper on a PCB layer."""

    SCHEMA = schemas.TRACE_SCHEMA

    net: Net
    layer: int
    vertices: List[QuantityVector]
