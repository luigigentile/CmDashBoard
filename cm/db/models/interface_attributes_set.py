from django.core.exceptions import ValidationError
from django.db import models

from cm.db import models as db_models
from cm.db.attribute_field import AttributeField

from .base_model import BaseModel


class InterfaceAttributesSet(BaseModel):
    """Attributes for a set of interfaces on a particular block and interface type."""

    block = models.ForeignKey(
        "db.Block", related_name="interface_attributes_sets", on_delete=models.CASCADE
    )
    interface_type = models.ForeignKey(
        "db.InterfaceType", related_name="attributes_sets", on_delete=models.CASCADE
    )
    interfaces = models.ManyToManyField(
        "db.Interface", related_name="attributes_sets", blank=True
    )

    # All interface attributes are stored schemalessly in a json field.
    attributes = AttributeField(blank=True, default=dict)

    def __str__(self):
        name = f"{self.block.name} {self.interface_type.name}"
        if self.pk:
            interfaces = ", ".join(
                interface.name for interface in self.interfaces.all()
            )
            return f"{name} ({interfaces})"
        return name

    def clean(self):
        """"Validate interface_type is used by one or more of the block's connectivity's interfaces."""
        if hasattr(self, "interface_type") and (
            not self.interface_type.interfaces.exists()
            or not self.interface_type.interfaces.filter(
                connectivity__block=self.block
            ).exists()
        ):
            raise ValidationError(
                {
                    "interface_type": "Interface type must be for one or more of the block's connectivity's interfaces"
                }
            )

    @staticmethod
    def attribute_definitions_from_data(data):
        """Get attribute definitions for a submitted interface type."""
        try:
            return db_models.InterfaceType.objects.get(
                id=data.get("interface_type_id")
            ).get_full_attributes()
        except db_models.InterfaceType.DoesNotExist:
            return {}

    def attribute_definitions(self):
        """Get attribute definitions for this set's interface type."""
        try:
            return self.interface_type.get_full_attributes()
        except db_models.InterfaceType.DoesNotExist:
            return None
