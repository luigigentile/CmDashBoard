from typing import List, Optional, cast
from uuid import UUID
from cm.db import models
from .connectivity import Connectivity
import strawberry
from strawberry.types import info

from django.db.models import Count
import datetime

#  DEFINISCE I TIPI DI DATO INPUT
#   INTERFACE type
@strawberry.type
class InterfaceType:
    id : UUID
    created:datetime.datetime
    name:str
    label : str

         
    @classmethod
    def from_db(self, myobj: models.InterfaceType) -> "InterfaceType":
        return self(
           id=myobj.id,
           created=myobj.created,
           label=myobj.label,
           name=myobj.name,
           )

    @classmethod
    def get_all(self,id: Optional[UUID]) -> List["InterfaceType"]:
        qs = models.InterfaceType.objects.all().order_by("name")
      
#       Filter by id        
        if id:
            qs = qs.filter(id=id)
#        qs = qs.filter(created__year=2019)
#        qs = qs.filter(created__month=12)
        return cast(List[InterfaceType], [self.from_db(interfaceType) for interfaceType in qs])

#   INTERFACE FAMILY
@strawberry.type
class InterfaceFamily:
    id : UUID
    created:datetime.datetime
    name:str
    label : str
    interfaceTypeCount : int
    interfaceType : List[InterfaceType]

         
    @classmethod
    def from_db(self, myobj: models.InterfaceFamily) -> "InterfaceFamily":
        
        return self(
           id=myobj.id,
           created=myobj.created,
           label=myobj.label,
           name=myobj.name,
           interfaceTypeCount = models.InterfaceType.objects.filter(family = myobj.id).count(),
           interfaceType = models.InterfaceType.objects.filter(family = myobj.id)

           )

    @classmethod
    def get_all(self,id: Optional[UUID]) -> List["InterfaceFamily"]:
        qs = models.InterfaceFamily.objects.all().order_by("name")
      
#       Filter by id        
        if id:
            qs = qs.filter(id=id)
#        qs = qs.filter(created__year=2019)
#        qs = qs.filter(created__month=12)
        return cast(List[InterfaceFamily], [self.from_db(interfaceFamily) for interfaceFamily in qs])
    






    



    
    


   
