from django import forms
from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from cm.db.constants import AncillaryAppliesTo
from cm.db.models import (
    Ancillary,
    ConnectionRule,
    Interface,
    InterfacePin,
    Pin,
    PinAssignment,
)

from .ancillary_admin import AncillaryInlineBaseForm
from .base_admin import BaseAdmin, BaseTabularInline


class AssignmentInline(BaseTabularInline):
    model = PinAssignment
    extra = 1
    fk_name = "interface"
    fields = [
        "interface_pin",
        "channel",
        "parent_interface_pin",
        "pin_identifiers",
        "pin_links",
    ]
    readonly_fields = ["pin_links"]

    def formfield_callback(self, db_field, formfield, request, parent=None):
        if db_field.name == "interface_pin" and parent is not None:
            formfield.queryset = InterfacePin.objects.filter(
                interface_type=parent.interface_type
            )
        if db_field.name == "pin" and parent is not None:
            formfield.queryset = Pin.objects.filter(connectivity=parent.connectivity)
        if db_field.name == "parent_interface_pin" and parent is not None:
            if parent.parent_id is None:
                formfield.queryset = InterfacePin.objects.none()
            else:
                formfield.queryset = InterfacePin.objects.filter(
                    interface_type=parent.parent.interface_type,
                )
        return formfield

    def pin_links(self, obj):
        links = []
        for pin in obj.pins.all():
            url = reverse("admin:db_pin_change", args=(pin.id,))
            links.append(f'<a href="{url}">{pin.name}</a> ({pin.number})')
        return mark_safe(f'{"<br/>".join(links)}')


class InterfaceForm(forms.ModelForm):
    class Meta:
        model = Interface
        fields = [
            "name",
            "connectivity",
            "parent",
            "interface_type",
            "channels",
            "is_required",
            "max_child_interfaces",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["parent"].queryset = Interface.objects.filter(
                connectivity_id=self.instance.connectivity_id,
                interface_type__allow_child_interfaces=True,
            )


class ConnectionRuleInline(BaseTabularInline):
    model = ConnectionRule
    extra = 1
    exclude = ["created_by", "interface_type"]


class AncillaryInline(BaseTabularInline):
    form = AncillaryInlineBaseForm
    model = Ancillary
    extra = 1
    show_change_link = True

    def formfield_callback(self, db_field, formfield, request, parent=None):
        if db_field.name == "pin" and parent is not None:
            formfield.queryset = parent.get_pins()
        if db_field.name == "applies_to":
            # Interfaces only allow configuring interface ancillaries
            db_field.choices = [
                (
                    AncillaryAppliesTo.interface,
                    AncillaryAppliesTo.labels[AncillaryAppliesTo.interface],
                )
            ]
            db_field.default = AncillaryAppliesTo.interface
        if db_field.name == "pin_assignment":
            formfield.queryset = PinAssignment.objects.filter(interface=parent)
        return formfield


@admin.register(Interface)
class InterfaceAdmin(BaseAdmin):
    inlines = [AssignmentInline, ConnectionRuleInline, AncillaryInline]
    search_fields = ["name", "interface_type__name"]
    form = InterfaceForm
    readonly_fields = [
        "connectivity_url",
        "inherited_ancillaries",
    ]
    fields = [
        "name",
        "connectivity_url",
        "function",
        "parent",
        "interface_type",
        "channels",
        "is_required",
        "inherited_ancillaries",
    ]

    def inherited_ancillaries(self, obj):
        ancillaries = obj.interface_type.ancillaries.all()
        if ancillaries:
            return mark_safe("<br/>".join(str(t) for t in ancillaries))
        else:
            return "None"

    def connectivity_url(self, obj):
        return format_html(
            '<a href="{}">{}</a>',
            reverse(
                "admin:db_connectivity_change",
                kwargs={"object_id": obj.connectivity_id},
            ),
            obj.connectivity,
        )

    connectivity_url.short_description = "Connectivity"  # type: ignore

    def get_fields(self, request, obj=None):
        """
        Hook for specifying fields.
        """
        if not obj or obj.interface_type.allow_child_interfaces:
            return self.fields + ["max_child_interfaces"]
        return self.fields

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)

        if obj and not obj.interface_type.can_be_required:
            form.base_fields["is_required"].disabled = True

        return form
