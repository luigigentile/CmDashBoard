from cm.db.fields import SmallTextField

from .base_model import BaseModel


class Manufacturer(BaseModel):
    class Meta:
        ordering = ("name", "id")

    name = SmallTextField()

    def __str__(self):
        return f"{self.name}"
