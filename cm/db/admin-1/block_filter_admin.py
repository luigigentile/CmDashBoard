from django.contrib import admin

from cm.db.admin.base_admin import BaseAdmin
from cm.db.admin.filter_query_admin import BaseFilterQueryInline
from cm.db.models import (
    AttributeDefinition,
    BlockFilter,
    Category,
    DirectAttributeDefinition,
)


class FilterQueryInline(BaseFilterQueryInline):
    def formfield_callback(self, db_field, formfield, request, parent=None):
        if db_field.name == "attribute_definition" and parent is not None:
            attribute_definition_ids = set()
            for category in Category.objects.filter(
                block__connectivity__id=parent.connectivity_id
            ):
                attribute_definition_ids.update(category.get_full_attribute_ids())

            # Also fetch global attributes
            attribute_definition_ids.update(
                DirectAttributeDefinition.objects.all().values_list("id", flat=True)
            )

            formfield.queryset = AttributeDefinition.objects.filter(
                id__in=attribute_definition_ids
            )
        return formfield


@admin.register(BlockFilter)
class BlockFilterAdmin(BaseAdmin):
    inlines = [FilterQueryInline]
    model = BlockFilter
    fields = ["reference"]
    show_change_link = True
