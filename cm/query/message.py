from typing import List, Optional, cast
from uuid import UUID

from django.db.models.fields import DateField
import strawberry
from graphql import GraphQLResolveInfo
from cm import models
from .tipoMessaggio import TipoMessaggio
from .destinatario import Destinatario
import datetime


@strawberry.type
class Message:
    id : int
    message: str
    creation_date : datetime.datetime
    tipo_messaggio : TipoMessaggio
    destinatari : List[Destinatario] 
        
    @classmethod
    def from_db(cls, db_message: models.Message) -> "Message":
        return cls(
            id= db_message.id,
            message=db_message.message,
            creation_date=db_message.creation_date,
            tipo_messaggio=db_message.tipo_messaggio,
            destinatari=db_message.destinatari.all()
        )

    @classmethod
    def get_all(cls) -> List["Message"]:
        qs = models.Message.objects.all()
        return cast(List[Message], [cls.from_db(message) for message in qs])
    
    @classmethod
    def get(cls,id) -> "Message":
        obj = models.Message.objects.get(id=id)
        return cast(Message, obj)


