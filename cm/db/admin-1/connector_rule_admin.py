from django.contrib import admin

from cm.db.admin.base_admin import BaseAdmin
from cm.db.admin.filter_query_admin import BaseFilterQueryInline
from cm.db.models import (
    AttributeDefinition,
    Category,
    ConnectorRule,
    DirectAttributeDefinition,
)


class FilterQueryInline(BaseFilterQueryInline):
    def formfield_callback(self, db_field, formfield, request, parent=None):
        if db_field.name == "attribute_definition":
            attribute_definition_ids = [
                attribute_id
                for category in Category.objects.filter(connector=True).all()
                for attribute_id in category.get_full_attribute_ids()
            ]

            # Also fetch global attributes
            attribute_definition_ids += list(
                DirectAttributeDefinition.objects.all().values_list("id", flat=True)
            )

            formfield.queryset = AttributeDefinition.objects.filter(
                id__in=attribute_definition_ids
            )
        return formfield


class FilterQueryFromInline(FilterQueryInline):
    verbose_name_plural = "From queries"
    fk_name = "connector_rule_from"


class FilterQueryToInline(FilterQueryInline):
    verbose_name_plural = "To queries"
    fk_name = "connector_rule_to"


@admin.register(ConnectorRule)
class ConnectorRuleAdmin(BaseAdmin):
    inlines = [FilterQueryFromInline, FilterQueryToInline]
    model = ConnectorRule
    fields = ["name"]
    show_change_link = True
