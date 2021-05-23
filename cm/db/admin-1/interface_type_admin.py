from copy import copy

from django import forms
from django.contrib import admin

from cm.db.constants import AncillaryAppliesTo
from cm.db.fields import SmallTextField
from cm.db.models import (
    Ancillary,
    AttributeDefinition,
    ConnectionRule,
    InterfacePin,
    InterfaceType,
)

from .ancillary_admin import AncillaryInlineBaseForm
from .base_admin import BaseAdmin, BaseTabularInline


class AttributeDefinitionInline(BaseTabularInline):
    model = AttributeDefinition
    extra = 1
    exclude = ["created_by", "category", "block_attribute"]


class InterfacePinInline(BaseTabularInline):
    model = InterfacePin
    extra = 1
    fields = [
        "reference",
        "pin_type",
        "sharing",
        "description",
        "is_required",
        "create_automatically",
        "parent_pins",
    ]

    def formfield_callback(self, db_field, formfield, request, parent=None):
        if db_field.name == "parent_pins" and parent is not None:
            formfield.queryset = InterfacePin.objects.filter(
                interface_type__in=parent.parents.all()
            )
        elif db_field.name == "compatible_pins" and parent is not None:
            formfield.queryset = InterfacePin.objects.filter(
                interface_type__in=parent.compatible_interface_types.all()
            )
        return formfield

    def get_fields(self, request, obj=None):
        """
        Hook for specifying fields.
        """
        fields = copy(self.fields)
        if obj and obj.pk and not obj.children.exists():
            # compatible pins are only defined on child interfaces
            # (it makes no sense to specify what "i2c" is compatible with, i2c master/slave have to define this)
            fields.append("compatible_pins")

        return fields


class ConnectionRuleInline(BaseTabularInline):
    model = ConnectionRule
    extra = 1
    exclude = ["created_by", "interface"]


class AncillaryInline(BaseTabularInline):
    form = AncillaryInlineBaseForm
    model = Ancillary
    exclude = (
        "interface",
        "pin",
    )
    extra = 1
    show_change_link = True

    def formfield_callback(self, db_field, formfield, request, parent=None):
        if db_field.name == "interface_pin" and parent is not None:
            formfield.queryset = InterfacePin.objects.filter(interface_type=parent)
        if db_field.name == "applies_to":
            # Interface types only allow configuring interface ancillaries
            db_field.choices = [
                (choice, label)
                for choice, label in db_field.choices
                if choice == AncillaryAppliesTo.interface
            ]
            db_field.default = AncillaryAppliesTo.interface
        return formfield


class InterfaceTypeForm(forms.ModelForm):
    def clean(self):
        """Ensure interface types share the same family."""
        try:
            InterfaceType.validate_parents(self.cleaned_data["parents"])
        except ValueError as e:
            raise forms.ValidationError({"parents": str(e)})


@admin.register(InterfaceType)
class InterfaceTypeAdmin(BaseAdmin):
    form = InterfaceTypeForm
    search_fields = ["name", "description"]
    list_filter = ["pins__reference", "pins__pin_type"]
    list_display = [
        "full_name",
        "label",
        "pins",
        "description",
        "function",
        "connection_rule_summary",
        "interface_bulk_input_pattern",
    ]
    inlines = [
        InterfacePinInline,
        AttributeDefinitionInline,
        ConnectionRuleInline,
        AncillaryInline,
    ]
    filter_horizontal = ["compatible_interface_types", "parents"]
    fields = [
        "name",
        "label",
        "description",
        "family",
        "can_be_required",
        "can_be_specialised",
        "function",
        "interface_bulk_input_pattern",
        "bulk_input_pattern",
        "allow_child_interfaces",
        "parents",
        "compatible_interface_types",
        "text_color",
        "background_color",
    ]

    formfield_overrides = {
        SmallTextField: {"widget": forms.widgets.TextInput(attrs={"size": 100})},
    }

    def pins(self, obj):
        return ", ".join([p.reference for p in obj.pins.all()])

    def connection_rule_summary(self, obj):
        return ", ".join(str(r) for r in obj.connection_rules.all())

    def formfield_callback(self, db_field, formfield, request, obj=None):
        if db_field.name == "parents" and obj is not None and obj.family is not None:
            formfield.queryset = obj.family.interface_types.all()
        if db_field.name == "compatible_interface_types" and obj is not None:
            if obj.family_id:
                # Types with families can only be compatible with types in the same family.
                formfield.queryset = formfield.queryset.filter(family=obj.family)
            else:
                # Types without families can only be compatible with themselves
                formfield.queryset = formfield.queryset.filter(id=obj.id)
        return formfield
