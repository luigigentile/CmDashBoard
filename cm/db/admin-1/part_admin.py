from autocompletefilter.admin import AutocompleteFilterMixin
from autocompletefilter.filters import AutocompleteListFilter
from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from cm.db.models import ConnectorRule, ManufacturerPart, Part

from .base_admin import BaseAdmin, BaseTabularInline
from .filters import MissingAttributeFilter
from .interface_attributes_set_admin import InterfaceAttributesSetInline


class ManufacturerPartInline(BaseTabularInline):
    model = ManufacturerPart
    extra = 1
    fields = ["manufacturer", "part_number"]


@admin.register(Part)
class PartAdmin(AutocompleteFilterMixin, BaseAdmin):
    fields = [
        "name",
        "categories",
        "connectivity",
        "description",
        "simplified_part",
        "attributes",
        "footprint",
        "manual_only",
        "created",
        "updated",
        "created_by",
    ]
    autocomplete_fields = ["connectivity", "categories"]
    list_filter = [
        ("categories", AutocompleteListFilter),
        ("manufacturer_parts__manufacturer", AutocompleteListFilter),
        ("connectivity", AutocompleteListFilter),
        "footprint",
        ("connectivity__interfaces__interface_type", AutocompleteListFilter),
        "created_by",
        "created",
        "updated",
        MissingAttributeFilter,
    ]
    list_display = [
        "name",
        "category_labels",
        "connectivity_url",
        "is_simplified",
        "created",
        "updated",
    ]
    ordering = ["-created"]

    search_fields = ["name", "manufacturer_parts__part_number", "categories__label"]
    show_duplicate = True
    readonly_fields = ["created", "updated", "created_by"]

    def get_inlines(self, request, obj=None):
        inlines = [
            ManufacturerPartInline,
        ]
        if obj:
            # Only show interface attribute inline for existing objects
            inlines.insert(0, InterfaceAttributesSetInline)

        return inlines

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.prefetch_related("categories").select_related("connectivity").cache()

    def connectivity_url(self, obj):
        return format_html(
            '<a href="{}">{}</a>',
            reverse(
                "admin:db_connectivity_change",
                kwargs={"object_id": obj.connectivity_id},
            ),
            obj.connectivity,
        )

    def category_labels(self, obj):
        return ", ".join(c.label for c in obj.categories.all().cache())

    category_labels.short_description = "Categories"  # type: ignore

    def is_simplified(self, obj):
        return "⚠️" if obj.simplified_part else ""

    def formfield_callback(self, db_field, formfield, request, parent=None):
        if db_field.name == "name":
            formfield.widget.attrs["size"] = 50
        return formfield

    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = extra_context or {}
        part = Part.objects.get(id=object_id)
        if part.is_connector:
            extra_context["compatible_connectors"] = self._compatible_connectors(part)
        return super().change_view(
            request, object_id, form_url, extra_context=extra_context,
        )

    def _compatible_connectors(self, connector):
        return [
            {
                "id": connector.id,
                "name": connector.name,
                "connectivity": connector.connectivity.name,
            }
            for connector in ConnectorRule.compatible_connectors(connector)
        ]
