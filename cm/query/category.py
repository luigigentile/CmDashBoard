from typing import List, Optional, cast
from uuid import UUID
from cm.db import models
from .connectivity import Connectivity
import strawberry
from strawberry.types import info

from django.db.models import Count
import datetime

#  DEFINISCE I TIPI DI DATO INPUT



##     CountCreated 
@strawberry.type
class CountCreated:
    created: datetime.date
    count: int

    @classmethod
    def from_dict(cls, obj) -> "CountCreated":
        return cls(
           count=obj["count"],
           created = obj['created']
        )
    @classmethod
    def count(cls) -> List["CountCreated"] :
        qs = models.Block.objects.values('created').annotate(count=Count('created'))
        return cast(List[CountCreated], [cls.from_dict(obj) for obj in qs])


@strawberry.type
class Category:
    id : UUID
    created:datetime.datetime
    label : str
    level:int
    parent: Optional[UUID]
    sonsCount : int
    allSonsCount :int
    allBlockCount : int
         
    @classmethod
    def from_db(self, myobj: models.Category) -> "Category":


 #         queryset = models.Block.objects.filter(
 #       categories__id__in=category.get_descendants(include_self=True).values_list(
 #           "id", flat=True
 #       ),   
#


        id=myobj.id,
        print(id[0])
#        categoryDescendeants =  models.Category.get_descendants(include_self=True).values_list("id", flat=True)        )
        categoryDescendeants =  models.Category.objects.get(id=id[0]).get_descendants(include_self=True)
#       objdiscendenti =  models.Category.objects.get(id="37D24E66-8145-4054-AD7B-11F3CFD8B298").get_descendants(include_self=False)

        for obj in categoryDescendeants:
            print(obj.label)
        allBlock = models.Block.objects.filter(categories__id__in=categoryDescendeants)
#        for obj in allBlock:
#            print(obj.name)
    #    parent = myobj.parent
        return self(
           id=myobj.id,
           created=myobj.created,
           label=myobj.label,
           level=myobj.level,
           parent = myobj.parent,
           sonsCount = models.Category.objects.filter(parent__in = id).count(),
           allSonsCount =  categoryDescendeants.count(),
           allBlockCount = allBlock.count()
            )

    @classmethod
    def get_all(self,id: Optional[UUID],orderBy:Optional[str]) -> List["Category"]:
#       order by clause
        if( orderBy == None ):
            qs = models.Category.objects.all().order_by("label")
        if(orderBy != None):
            qs = models.Category.objects.all().order_by(orderBy)
#       Filter by id        
        if id:
            qs = qs.filter(id=id)
#        qs = qs.filter(created__year=2019)
#        qs = qs.filter(created__month=12)
        return cast(List[Category], [self.from_db(category) for category in qs])
    

    @classmethod
    def get(cls,id) -> "Category":
        print("id=")
        obj = models.Category.objects.get(id=id)
        return cast(Category, obj)


    
    


   
