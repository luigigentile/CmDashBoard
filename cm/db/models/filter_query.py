from copy import copy

from django.core.exceptions import ValidationError
from django.db import models

from cm.db.attribute_field.transform import decode_form_value
from cm.db.constants import OPERATOR_SYMBOLS, FilterOperator
from cm.db.fields import SmallTextField
from cm.db.models.base_model import BaseModel


class FilterQuery(BaseModel):
    """Describes a query for filtering parts on subcircuits and connector rules.

    Multiple of these queries can combine to filter multiple attributes, etc.
    """

    attribute_definition = models.ForeignKey(
        "db.AttributeDefinition", on_delete=models.PROTECT
    )
    operator = SmallTextField(choices=FilterOperator.choices)
    value = SmallTextField()

    # Filter queries can either be on sub-circuit block filters,
    # or a connector rule's "from"/"to" queries
    block_filter = models.ForeignKey(
        "db.BlockFilter",
        related_name="queries",
        blank=True,
        null=True,
        on_delete=models.CASCADE,
    )
    connector_rule_from = models.ForeignKey(
        "db.ConnectorRule",
        related_name="from_queries",
        blank=True,
        null=True,
        on_delete=models.CASCADE,
    )
    connector_rule_to = models.ForeignKey(
        "db.ConnectorRule",
        related_name="to_queries",
        blank=True,
        null=True,
        on_delete=models.CASCADE,
    )

    def __str__(self):
        return OPERATOR_SYMBOLS[self.operator].format(
            field=self.attribute_definition.name, value=self.value
        )

    def clean(self):
        """Validate that value is valid for the attribute definition."""
        if self.attribute_definition_id is None or self.value is None:
            return

        try:
            decode_form_value(
                self.attribute_definition.name, self.value, self.attribute_definition
            )
        except ValueError as e:
            raise ValidationError({"value": str(e)})

    def save(self, *args, **kwargs):
        """Ensure that one, and only one, foreign key relation is set."""
        relations = sum(
            (
                self.block_filter_id is not None,
                self.connector_rule_from_id is not None,
                self.connector_rule_to_id is not None,
            )
        )
        if relations == 0:
            raise ValidationError(
                "A block filter or connector rule from/to must be set"
            )
        elif relations > 1:
            raise ValidationError(
                "Only one of block filter, connector rule from or connector rule to may be set"
            )
        super().save(*args, **kwargs)

    def duplicate(self, filter_id):
        """Create a duplicate instance of this query, attached to the filter with id <filter_id>."""
        duplicate_instance = copy(self)
        duplicate_instance.pk = None
        duplicate_instance.filter_id = filter_id
        duplicate_instance.save()
