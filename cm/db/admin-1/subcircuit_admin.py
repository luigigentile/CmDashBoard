from autocompletefilter.admin import AutocompleteFilterMixin
from autocompletefilter.filters import AutocompleteListFilter
from django import forms
from django.contrib import admin
from django.utils.safestring import mark_safe

from cm.db.admin.bus_fragment_admin import BusFragmentForm
from cm.db.constants import AncillaryAppliesTo
from cm.db.models import (
    Ancillary,
    BlockFilter,
    BusFragment,
    Interface,
    InterfacePin,
    Pin,
    PinAssignment,
    PinUse,
    SubCircuit,
)

from .base_admin import BaseAdmin, BaseTabularInline
from .interface_attributes_set_admin import InterfaceAttributesSetInline


class FilterInline(BaseTabularInline):
    model = BlockFilter
    extra = 1
    fields = ["reference", "connectivity", "queries"]
    readonly_fields = ["queries"]
    show_change_link = True
    verbose_name = "Child"
    verbose_name_plural = "Children"

    def queries(self, obj):
        queries = [str(query) for query in obj.queries.all()]
        return mark_safe("<br>".join(queries))

    queries.short_description = "Filters"  # type: ignore


class BusFragmentInline(BaseTabularInline):
    model = BusFragment
    form = BusFragmentForm
    extra = 1
    show_change_link = True

    def formfield_callback(self, db_field, formfield, request, obj=None):
        # We have to override the queryset from BusFragmentForm
        if db_field.name in ("from_filter", "to_filter") and obj is not None:
            formfield.queryset = obj.children.all()
        return formfield


class AncillaryInline(BaseTabularInline):
    model = Ancillary
    extra = 1
    show_change_link = True
    fields = [
        "ancillary_type",
        "applies_to",
        "connectivity",
        "interface",
        "interface_type",
        "interface_family",
        "maximum_latency",
    ]

    def formfield_callback(self, db_field, formfield, request, parent=None):
        if db_field.name == "interface" and parent is not None:
            formfield.required = True
            formfield.queryset = Interface.objects.filter(
                connectivity__block_filters__subcircuit=parent
            ).distinct()
        if db_field.name == "interface_pin" and parent is not None:
            formfield.queryset = InterfacePin.objects.filter(
                interface_type__interfaces__connectivity__block_filters__subcircuit=parent
            ).distinct()
        if db_field.name == "pin_assignment" and parent is not None:
            formfield.queryset = PinAssignment.objects.filter(
                interface__connectivity__block_filters__subcircuit=parent
            ).distinct()
        if db_field.name == "applies_to":
            # Sub-circuits only allow configuring interface and pin ancillaries
            db_field.choices = [
                (
                    AncillaryAppliesTo.interface,
                    AncillaryAppliesTo.labels[AncillaryAppliesTo.interface],
                ),
                (
                    AncillaryAppliesTo.pins,
                    AncillaryAppliesTo.labels[AncillaryAppliesTo.pins],
                ),
            ]
            db_field.default = AncillaryAppliesTo.interface
        return formfield

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "interface":
            return InterfaceChoiceField(
                queryset=Interface.objects.all().order_by("connectivity__name"),
                required=False,
            )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class PinUseInlineForm(forms.ModelForm):
    class Meta:
        model = PinUse
        fields = [
            "block_filter",
            "interface",
            "interface_pin",
            "pin",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        interface_qs = self.fields["interface"].queryset
        interface_pin_qs = self.fields["interface_pin"].queryset
        pin_qs = self.fields["pin"].queryset

        # Filter interfaces if connectivity is given
        if self.instance.block_filter_id and self.instance.block_filter.connectivity_id:
            interface_qs = interface_qs.filter(
                connectivity=self.instance.block_filter.connectivity
            )

        # Filter interface pins if interface is given
        if self.instance.interface_id:
            interface_pin_qs = interface_pin_qs.filter(
                interface_type=self.instance.interface.interface_type
            )

        # Filter pins if interface and interface pin are given

        if self.instance.interface_pin_id and self.instance.interface_id:
            pin_qs = pin_qs.filter(
                connectivity__interfaces__pin_assignments__interface_pin=self.instance.interface_pin
            ).filter(connectivity__interfaces=self.instance.interface)

        self.fields["interface"].queryset = interface_qs.distinct()
        self.fields["interface_pin"].queryset = interface_pin_qs.distinct()
        self.fields["pin"].queryset = pin_qs.distinct()


class InterfaceChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f"{obj} - ({obj.connectivity})"


class PinChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f"{obj} - ({obj.connectivity})"


class PinUseInline(BaseTabularInline):
    form = PinUseInlineForm
    model = PinUse
    extra = 1
    show_change_link = True

    def formfield_callback(self, db_field, formfield, request, parent=None):
        if db_field.name == "block_filter" and parent is not None:
            formfield.required = True
            formfield.queryset = BlockFilter.objects.filter(
                subcircuit=parent
            ).distinct()
        if db_field.name == "interface" and parent is not None:
            formfield.queryset = Interface.objects.filter(
                connectivity__block_filters__subcircuit=parent
            ).distinct()
        if db_field.name == "interface_pin" and parent is not None:
            formfield.queryset = InterfacePin.objects.filter(
                interface_type__interfaces__connectivity__block_filters__subcircuit=parent
            ).distinct()
        if db_field.name == "pin" and parent is not None:
            formfield.queryset = Pin.objects.filter(
                connectivity__block_filters__subcircuit=parent
            ).distinct()
        return formfield

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "interface":
            return InterfaceChoiceField(queryset=Interface.objects.all())
        if db_field.name == "pin":
            return PinChoiceField(queryset=Pin.objects.all())
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(SubCircuit)
class SubCircuitAdmin(AutocompleteFilterMixin, BaseAdmin):
    inlines = [
        FilterInline,
        InterfaceAttributesSetInline,
        BusFragmentInline,
        AncillaryInline,
        PinUseInline,
    ]
    fields = [
        "name",
        "categories",
        "connectivity",
        "attributes",
        "manual_only",
    ]
    autocomplete_fields = ["connectivity", "categories"]
    list_filter = [
        ("categories", AutocompleteListFilter),
        ("connectivity", AutocompleteListFilter),
        ("connectivity__interfaces__interface_type", AutocompleteListFilter),
        "created",
        "updated",
        "created_by",
    ]
    list_display = ["name", "category_labels", "connectivity", "created", "updated"]
    search_fields = ["name", "categories__label"]
    show_duplicate = True
    verbose_name = "Sub-circuit"

    def get_inline_instances(self, request, obj=None):
        if not obj:
            # Only show filters on edit, not create
            return []
        return super().get_inline_instances(request, obj=obj)

    def category_labels(self, obj):
        return ", ".join(c.label for c in obj.categories.all())

    category_labels.short_description = "Categories"  # type: ignore

    def formfield_callback(self, db_field, formfield, request, parent=None):
        if db_field.name == "name":
            formfield.widget.attrs["size"] = 50
        return formfield
