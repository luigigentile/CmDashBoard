from django.contrib.admin import SimpleListFilter

from cm.db.attribute_field import AttributeField
from cm.db.models import AttributeDefinition


class MissingAttributeFilter(SimpleListFilter):
    # template = 'django_admin_listfilter_dropdown/dropdown_filter.html'
    title = "Missing Attribute"  # or use _('country') for translated title
    parameter_name = "attribute"

    def lookups(self, request, model_admin):
        attribute_definitions = AttributeDefinition.objects.all().order_by("name")
        return [(d.id, f"{d.name} ({d.category})") for d in attribute_definitions]

    def queryset(self, request, queryset):
        if self.value():
            attribute_definition = AttributeDefinition.objects.get(id=self.value())
            return queryset.filter(
                AttributeField.lookup_missing(attribute_definition.name)
            )
