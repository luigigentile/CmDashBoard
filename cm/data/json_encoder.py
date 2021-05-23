import json
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import UUID

from cm.data import ranges, serializable, units, vector
from cm.data.component import Component


class DataEncoder(json.JSONEncoder):
    """Custom JSON encoder that can deal with our various custom data types.

    This is mostly used for debugging."""

    def default(self, obj: Any) -> Any:
        if isinstance(obj, units.Quantity):
            return str(obj)
        if isinstance(obj, ranges.Range):
            return str(obj)
        if isinstance(obj, serializable.Serializable):
            return obj.to_data()
        if isinstance(obj, Component):
            # FIXME: We have to have this because component is not a serializable anymore,
            # but it's a bit messy and we might want to rethink this whole encoder business.
            return {
                "reference": obj.reference,
                "block": obj.block.id if obj.block else None,
                "children": {c.reference: c.to_data() for c in obj.children},
            }
        if isinstance(obj, Enum):
            return obj.value
        if isinstance(obj, Path):
            return str(obj)
        if isinstance(obj, vector.QuantityVector):
            return {"x": obj.x, "y": obj.y, "z": obj.z}
        if isinstance(obj, vector.Vector):
            return {"x": obj.x, "y": obj.y, "z": obj.z}
        if isinstance(obj, UUID):
            return str(obj)
        if isinstance(obj, set):
            return list(obj)
        return super().default(obj)
