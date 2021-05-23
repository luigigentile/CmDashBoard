from typing import List, Optional, cast
from uuid import UUID
from cm.db import models
import strawberry

from django.db.models import Count
import datetime

#  DEFINISCE I TIPI DI DATO INPUT
#   INTERFACE type
@strawberry.type
class ManufacturerType:
    id : UUID
    created:datetime.datetime
    name:str
    partCount:int
         
    @classmethod
    def from_db(self, myobj: models.Manufacturer) -> "ManufacturerType":
        return self(
           id=myobj.id,
           created=myobj.created,
           name=myobj.name,
           partCount = models.ManufacturerPart.objects.filter(manufacturer = myobj.id).count(),
           )

    @classmethod
    def get_all(self,id: Optional[UUID]) -> List["ManufacturerType"]:
        qs = models.Manufacturer.objects.all().order_by("name")
      
#       Filter by id        
        if id:
            qs = qs.filter(id=id)
        return cast(List[ManufacturerType], [self.from_db(manufacturer) for manufacturer in qs])

