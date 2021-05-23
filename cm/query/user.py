import strawberry
from graphql import GraphQLResolveInfo


@strawberry.type
class User:
    username: str
    email: str
    first_name: str
    last_name: str
    is_superuser: bool

    @classmethod
    def get_current(cls, info: GraphQLResolveInfo) -> "User":
         
        
        print(dir(info.context["request"]))
        print(info.context.request.user.email)
        for prop in info.context["request"]:
            print("prop=" + str(prop))

        user = info.context["request"].user
        return cls(
            username=user.username,
            email=user.email,
            first_name=user.first_name,
            last_name=user.last_name,
            is_superuser=user.is_superuser,
        )











#from typing import List, Optional, cast
#from cm import models
#import strawberry
#from graphql import GraphQLResolveInfo
#from django.contrib.auth.models import User 
#
#@strawberry.type
#class UserType:
#    username: str
#    email: str
#    first_name: str
#    last_name: str
#    is_superuser: bool
#
#    @classmethod
#    def get_current(cls, info: GraphQLResolveInfo) -> "User":
#        user = info.context["request"].user
#        print("current user is" + user.username)
#        qs = User.objects.all()
#        for myuser in qs:
#            print("user is " + myuser.username)
#        return cls(
#            username=user.username,
#            email=user.email,
#            first_name=user.first_name,
#            last_name=user.last_name,
#            is_superuser=user.is_superuser,
#        )
#     
    
#    @classmethod
#    def from_db(cls, db_user: User) -> "UserType":
#        print("sono in ...." + db_user.username)
#        return cls(
#            username=db_user.username,
#            email=db_user.email,
#            first_name=db_user.first_name,
#            last_name=db_user.last_name,
#            is_superuser=db_user.is_superuser,
#             )
#        
#    @classmethod
#    def get_users(cls, info: GraphQLResolveInfo) -> List["UserType"]:
#        qs = User.objects.all()
#        for user in qs:
#            print("user is " + user.username)
#   
#        return cast(List[UserType], [cls.from_db(user) for user in qs])
   