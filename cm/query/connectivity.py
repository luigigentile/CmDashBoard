from typing import List, Optional, cast
from uuid import UUID
from cm.db import models
import strawberry
import datetime


##     Count Block by Type 
@strawberry.type
class CountBlockConnectivity:
    count: int

    @classmethod
    def count(cls) -> 'CountBlockConnectivity' :
        conta = models.Block.objects.all().count()
     
        return cls(conta)



@strawberry.type
class Connectivity:
    id: UUID
    name: str
    simplified_connectivity: str
    use_for_ancillaries: bool
    created:datetime.datetime
  
    @classmethod
    def from_db(cls, db_connectivity: models.Connectivity) -> "Connectivity":
        return cls(
            id=db_connectivity.id,
            name=db_connectivity.name,
            created=db_connectivity.created,
            simplified_connectivity=db_connectivity.simplified_connectivity,
            use_for_ancillaries=db_connectivity.use_for_ancillaries,
        )

    @classmethod
    def get_all(cls) -> List["Connectivity"]:
        qs = models.Connectivity.objects.all()
        print(qs)
        return cast(List[Connectivity], [cls.from_db(connectivity) for connectivity in qs])