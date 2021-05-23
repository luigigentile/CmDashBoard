from django.db.models.fields import BooleanField

from cm.db.fields import SmallTextField

from .base_model import BaseModel


class Distributor(BaseModel):
    name = SmallTextField(unique=True)
    skus_priced_on_same_scale = BooleanField(
        verbose_name="Different SKU quantities are mixed when determining price",
    )

    def __str__(self):
        return self.name
