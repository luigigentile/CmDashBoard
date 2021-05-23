from typing import List, Optional, cast
from uuid import UUID
from cm.db import models
from .connectivity import Connectivity
from .category import Category
import strawberry
from django.db.models import Count
import datetime
from mptt.models import MPTTModel, TreeForeignKey, TreeManager

#  DEFINISCE I TIPI DI DATO INPUT

##     Count Block by Type 
@strawberry.type
class CountBlockType:
    blockType: str
    count: int

    @classmethod
    def from_dict(cls, obj) -> "CountBlockType":
        return cls(
           count=obj["count"],
           blockType = obj['block_type']
        )
    @classmethod
    def count(cls) -> List["CountBlockType"] :
        qs = models.Block.objects.values('block_type').annotate(count=Count('block_type'))
        return cast(List[CountBlockType], [cls.from_dict(obj) for obj in qs])
    
    @classmethod
    def countDescendant(cls) -> ["CountBlockType"] :
        return cls(
            count = models.Category.get_descendant_count(),
            blockType = "aa"
        )

      
    


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
class Block:
    id : UUID
    name : str
    block_type : str
    manual_only : bool
    created  : datetime.datetime
    connectivity : Connectivity
    categories: List[Category]
        
    @classmethod
    def from_db(cls, myobj: models.Block) -> "Block":
        return cls(
           name=myobj.name,
           id=myobj.id,
           block_type = myobj.block_type,
           manual_only = myobj.manual_only,
           created = myobj.created.date(),
           connectivity = myobj.connectivity,
           categories = myobj.categories.all(),
    )

    @classmethod
    def get_all(self,id: Optional[UUID],
    limit: Optional[int],
    orderBy:Optional[str]) -> List["Block"]:
#       LIMIT ARGUMENTS
        if( limit == None ):
            limit = 50000


#       ORDER BY CLAUSE
        if( orderBy == None ):
            qs = models.Block.objects.all().order_by("created")[:limit]
        if(orderBy != None):
            qs = models.Block.objects.all().order_by(orderBy)[:limit]
#       ID ARGUMENTS        
        if id:
            qs = qs.filter(id=id)



#        qs = models.Block.objects.all().order_by("created")
#        qs = qs.filter(created__year=2019)
#        qs = qs.filter(created__month=12)
        return cast(List[Block], [self.from_db(block) for block in qs])


   
