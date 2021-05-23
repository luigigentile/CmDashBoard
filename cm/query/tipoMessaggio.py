from typing import List, Optional, cast
from cm import models
import strawberry

@strawberry.type
class TipoMessaggio:
    id : int
    tipo : str
        
    @classmethod
    def from_db(cls, myobj: models.TipoMessaggio) -> "TipoMessaggio":
        return cls(
            id= myobj.id,
            tipo=myobj.tipo,
        )

    @classmethod
    def get_all(cls) -> List["TipoMessaggio"]:
        qs = models.TipoMessaggio.objects.all()
        return cast(List[TipoMessaggio], [cls.from_db(tipomessaggio) for tipomessaggio in qs])
