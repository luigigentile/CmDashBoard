from django.db import models

from cm.db.fields import SmallTextField

from .base_model import BaseModel
from .category import Category


class Footprint(BaseModel):
    name = SmallTextField()
    category = models.ForeignKey(Category, on_delete=models.PROTECT)
    source_file = SmallTextField(
        help_text=(
            "Temporary field to allow storing the local path of a component file. \n"
            "Note this only exists to allow the software to keep working while we transition to everything being "
            "stored in the database."
        )
    )

    def __str__(self):
        return self.name
