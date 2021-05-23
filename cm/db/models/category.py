from typing import Any, Dict, Optional, Set, cast
from uuid import UUID

from colorfield.fields import ColorField
from django.core.exceptions import ValidationError
from django.db import models
from django.template.defaultfilters import slugify
from mptt.models import MPTTModel, TreeForeignKey, TreeManager

from cm.db.fields import SmallTextField
from cm.db.models import AttributeDefinition

from .base_model import BaseModel


class Category(BaseModel, MPTTModel):
    class Meta:
        verbose_name_plural = "Categories"

    class MPTTMeta:
        order_insertion_by = ["slug"]

    label = SmallTextField()
    slug = models.SlugField(unique=True)
    parent = TreeForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True, related_name="children"
    )
    objects = TreeManager()
    reference_label = SmallTextField(
        blank=True,
        help_text="Reference letter used for this category of part in schematics (e.g. R,C,...)",
    )
    background_color = ColorField(null=True, blank=True)
    width = models.FloatField(
        null=True,
        blank=True,
        help_text='Default width for requirements of this category (in "rem")',
    )
    height = models.FloatField(
        null=True,
        blank=True,
        help_text='Default height for requirements of this category (in "rem")',
    )
    connector = models.BooleanField(
        default=False,
        help_text="Parts with this category (and all descendent categories) can be used as connectors",
    )
    icon = models.FileField(
        blank=True, null=True, upload_to="category_icons", help_text="SVG files only",
    )

    def __str__(self):
        return self.label

    def clean(self):
        if self.parent_id:
            # Check that the category hierarchy is valid
            new_parent = Category.objects.get(id=self.parent_id)
            new_ancestors = list(new_parent.get_ancestors()) + [new_parent]
            if self in new_ancestors:
                raise ValidationError(
                    {"parent": "A category cannot have itself as an ancestor!"}
                )

        # If this category is a connector ensure all descendent categories are too
        if self.connector:
            if self.id and self.get_descendants().exclude(connector=True).exists():
                raise ValidationError(
                    {"connector": "All descendent categories must also be connectors"}
                )

        # Otherwise, ensure all ancestor categories are not connectors
        else:
            if (
                self.parent_id
                and self.parent.get_ancestors(include_self=True)
                .filter(connector=True)
                .exists()
            ):
                raise ValidationError(
                    {"connector": "One or more ancestor categories are connectors"}
                )

    def save(self, *args, **kwargs):
        self.slug = self.slug or slugify(self.label)
        super().save(*args, **kwargs)

    def get_attributes(self) -> Dict[str, AttributeDefinition]:
        """Return the attibute definitions for this category, indexed by attribute name."""
        return {attribute.name: attribute for attribute in self.attributes.all()}

    def get_attribute_ids(self) -> Set[UUID]:
        """Like get_attributes, but returns only the ids of the category's attributes."""
        return cast(Set[UUID], set(self.attributes.all().values_list("id", flat=True)),)

    def get_full_attributes(self) -> Dict[str, AttributeDefinition]:
        """Return the attribute definitions for this category and its ancestors."""
        full_attributes: Dict[str, AttributeDefinition] = {}

        ancestors = self.get_ancestors(include_self=True)
        for ancestor in ancestors:
            full_attributes.update(ancestor.get_attributes())
        return full_attributes

    def get_full_attribute_ids(self) -> Set[UUID]:
        full_attribute_ids: Set[UUID] = set()

        ancestors = self.get_ancestors(include_self=True)
        for ancestor in ancestors:
            full_attribute_ids |= ancestor.get_attribute_ids()
        return full_attribute_ids

    def get_background_color(self):
        """Return the background color of this category, defaulting back to parent colors."""
        if self.background_color:
            return self.background_color
        return (
            self.get_ancestors()
            .filter(background_color__isnull=False)
            .values_list("background_color", flat=True)
            .last()
        )

    def subcategory_ids(self, include_self=False):
        descendant_ids = self.get_descendants(include_self=include_self).values_list(
            "id", flat=True
        )
        return descendant_ids

    def closest_ancestor_value(
        self, field_name: str, exclude: Any = None, include_self: bool = True
    ) -> Optional[Any]:
        """Iterate up through ancestors (by default including ourselves) and find the first
        valid value (where validity is defined as not matching the value of "exclude")"""
        return (
            self.get_ancestors(ascending=True, include_self=include_self)
            .exclude(**{field_name: exclude})
            .values_list(field_name, flat=True)
            .first()
        )

    def get_reference_label(self) -> str:
        """Return the appropriate reference label for this category.

        The label is either this category's label, or the label of the closest ancestor with a label.
        If no ancestors have a label, we fall back to the default label 'U'
        """
        if self.reference_label:
            return self.reference_label
        return (
            self.closest_ancestor_value(
                "reference_label", exclude="", include_self=False
            )
            or "U"
        )
