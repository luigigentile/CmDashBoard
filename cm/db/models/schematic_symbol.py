from django.db import models

from cm.db.fields import SmallTextField

from .base_model import BaseModel
from .category import Category


class SchematicSymbol(BaseModel):
    name = SmallTextField()
    category = models.ForeignKey(Category, on_delete=models.PROTECT)

    def __str__(self):
        return self.name
