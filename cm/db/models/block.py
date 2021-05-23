from typing import Any, Dict, cast

from django.db import models
from djchoices import ChoiceItem, DjangoChoices
from mptt.fields import TreeManyToManyField

from cm.db.attribute_field import AttributeField
from cm.db.fields import SmallTextField

from .attribute_definition import AttributeDefinition
from .base_model import BaseModel
from .category import Category
from .footprint import Footprint
from .pin import Pin

PadReference = str


class Block(BaseModel):
    class BlockType(DjangoChoices):
        part = ChoiceItem("part", "Part")
        subcircuit = ChoiceItem("subcircuit", "Sub-circuit")

    name = SmallTextField(unique=True)
    description = models.TextField(blank=True, default="")
    block_type = models.CharField(max_length=10, choices=BlockType.choices)
    categories = TreeManyToManyField("db.Category")

    # All block attributes are stored schemalessly in a json field.
    # What fields and values are allowed depends on the block category.
    attributes = AttributeField(blank=True, default=dict)

    connectivity = models.ForeignKey("db.Connectivity", related_name="blocks",on_delete=models.PROTECT)

    # ###### Part-specific fields (enforced in proxy model) ########
    # Parts (but not sub-circuits) have footprints, so this field applies to parts only.
    footprint = models.ForeignKey(
        Footprint, on_delete=models.PROTECT, blank=True, null=True
    )
    footprint_mapping = models.JSONField(
        help_text="Mapping of connectivity pins to footprint pads",
        blank=True,
        default=dict,
    )

    simplified_part = models.TextField(
        "Simplified part notes",
        help_text=(
            "If this part differs in function from its datasheet or is otherwise simplified to overcome "
            "software limitations, please add some notes about this here."
        ),
        blank=True,
        default="",
    )

    manual_only = models.BooleanField(
        "Manual Only",
        help_text="This part should not be usable in the frontend",
        default=False,
    )

    @property
    def is_part(self) -> bool:
        return cast(bool, self.block_type == self.BlockType.part)

    @property
    def is_subcircuit(self) -> bool:
        return cast(bool, self.block_type == self.BlockType.subcircuit)

    def get_pad(self, pin: Pin) -> PadReference:
        return str(self.footprint_mapping[str(pin.id)])

    def __str__(self) -> str:
        return str(self.name)

    def get_category(self) -> Category:
        """Return the block's root category, which is the closest common ancestor of all its categories."""
        category_ancestors = zip(
            *[c.get_ancestors(include_self=True) for c in self.categories.all()]
        )

        if not category_ancestors:
            raise RuntimeError(f"Block {self} has no category!")

        common_ancestor = None
        for level_ancestors in category_ancestors:
            all_ancestors_the_same = len(set([a.id for a in level_ancestors])) == 1
            if all_ancestors_the_same:
                common_ancestor = level_ancestors[0]
            else:
                break

        if not common_ancestor:
            raise RuntimeError(f"Block {self}'s categories have no common ancestor!")

        return cast(Category, common_ancestor)

    @staticmethod
    def _attribute_definitions(
        categories: models.QuerySet,
    ) -> Dict[str, AttributeDefinition]:
        """Fetch all attribute definitions for the specified categories."""
        attribute_definitions: Dict[str, AttributeDefinition] = {}
        for category in categories:
            attribute_definitions.update(category.get_full_attributes())

        return attribute_definitions

    @staticmethod
    def attribute_definitions_from_data(
        data: Dict[str, Any]
    ) -> Dict[str, AttributeDefinition]:
        """Get attribute definitions for a submitted set of categories."""
        return Block._attribute_definitions(
            Category.objects.filter(id__in=data.get("categories_ids", [])),
        )

    def attribute_definitions(self) -> Dict[str, AttributeDefinition]:
        """Get attribute definitions for this block's categories."""
        if self.categories.exists():
            return Block._attribute_definitions(self.categories.all())
        else:
            return {}
