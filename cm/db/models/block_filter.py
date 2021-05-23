from copy import copy

from django.db import models

from cm.db.fields import SmallTextField
from cm.db.models.base_model import BaseModel


class BlockFilter(BaseModel):
    reference = SmallTextField(
        help_text="Local reference (only valid within sub-circuit)."
    )
    category = models.ForeignKey(
        "db.Category", related_name="block_filters", on_delete=models.PROTECT,
    )
    connectivity = models.ForeignKey(
        "db.Connectivity",
        blank=True,
        null=True,
        related_name="block_filters",
        on_delete=models.PROTECT,
        help_text="Specify a connectivity to be able to specify concrete interfaces in buses.",
    )
    subcircuit = models.ForeignKey(
        "db.SubCircuit", related_name="children", on_delete=models.CASCADE
    )

    def __str__(self):
        return self.reference

    def duplicate(self, subcircuit_id):
        duplicate_instance = copy(self)
        duplicate_instance.pk = None
        duplicate_instance.subcircuit_id = subcircuit_id
        duplicate_instance.save()

        # Duplicate the filter's query objects
        for query in self.queries.all():
            query.duplicate(filter_id=duplicate_instance.pk)

        return duplicate_instance
