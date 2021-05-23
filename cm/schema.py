import typing
import asyncio
from uuid import UUID
import strawberry

from typing import List, Optional, cast
from graphql import GraphQLResolveInfo

from .query import (
    Block,
    Connectivity,
    CountBlockType,
    CountCreated,
    CountBlockConnectivity,
    Category,
    User,
    InterfaceType,
    InterfaceFamily,
    ManufacturerType,
   )


@strawberry.type
class Query:

   @strawberry.field
   def user(self, info: GraphQLResolveInfo) -> User:
        return User.get_current(info)
 

#   all blocks
   @strawberry.field
   def all_block(self,id: Optional[UUID] = None,
               limit: Optional[int] = None,
               orderBy: Optional[str] = None) ->  List["Block"]:
        return Block.get_all(id,limit,orderBy)


   @strawberry.field
   def countBlockType(self) ->  List["CountBlockType"]:
        return CountBlockType.count()

   @strawberry.field
   def countDescendantAllBlock(self) ->  List["CountBlockType"]:
        return CountBlockType.countDescendant()



   @strawberry.field
   def countCreated(self) ->  List["CountCreated"]:
        return CountCreated.count()

#   all connectivity
   @strawberry.field
   def all_connectivity(self) ->  List["Connectivity"]:
        return Connectivity.get_all()

   @strawberry.field
   def count_blockConnectivity(self) ->  CountBlockConnectivity:
        return CountBlockConnectivity.count()
 
#   all category 
   @strawberry.field
   def all_category(self,
          id: Optional[UUID] = None,
          orderBy: Optional[str] = None) ->  List["Category"]:
        return Category.get_all(id,orderBy)


   @strawberry.field
   def category(self,id:UUID) ->  "Category":
        print("category")
        return Category.get(id)  


#         INTERFACE
#   Interface FAMILY
   @strawberry.field
   def all_interface_family(self,
          id: Optional[UUID] = None,) ->  List["InterfaceFamily"]:
        return InterfaceFamily.get_all(id)



#   Interface Type
   @strawberry.field
   def all_interface_type(self,
          id: Optional[UUID] = None,) ->  List["InterfaceType"]:
        return InterfaceType.get_all(id)


#   Interface Type
   @strawberry.field
   def all_manufacturer(self,
          id: Optional[UUID] = None,) ->  List["ManufacturerType"]:
        return ManufacturerType.get_all(id)



schema = strawberry.Schema(query=Query)




