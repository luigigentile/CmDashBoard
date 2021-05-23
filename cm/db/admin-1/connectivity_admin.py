from autocompletefilter.admin import AutocompleteFilterMixin
from autocompletefilter.filters import AutocompleteListFilter
from django import forms
from django.contrib import admin, messages
from django.urls import reverse
from django.utils.safestring import mark_safe

from cm.db.constants import InterfaceFunction
from cm.db.models import Connectivity, Interface, Pin

from .base_admin import BaseAdmin, BaseTabularInline
from .spreadsheet_input import process_connectivity_input


class InterfaceForm(forms.ModelForm):
    class Meta:
        model = Interface
        fields = ["name", "interface_type", "is_required"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance._state.adding:
            self.fields["interface_type"].disabled = True


class InterfaceInline(BaseTabularInline):
    form = InterfaceForm
    model = Interface
    extra = 1
    show_change_link = True
    fields = [
        "name",
        "parent",
        "interface_type",
        "function",
        "is_required",
        "all_ancillaries",
        "connection_rules_summary",
    ]
    readonly_fields = [
        "connection_rules_summary",
        "parent",
        "all_ancillaries",
    ]

    def connection_rules_summary(self, obj):
        rules = obj.get_connection_rules()
        return ", ".join(str(r) for r in rules)

    def all_ancillaries(self, obj):
        ancillaries = obj.get_ancillaries()
        return ", ".join(t.ancillary_type for t in ancillaries)

    all_ancillaries.short_descriptions = "Ancillary"  # type: ignore


class PinInline(BaseTabularInline):
    model = Pin
    extra = 1
    fields = ["number", "name", "pin_type", "voltage_reference"]
    show_change_link = True

    def formfield_callback(self, db_field, formfield, request, parent=None):
        if db_field.name == "voltage_reference" and parent is not None:
            formfield.queryset = Interface.objects.filter(
                Interface.function_lookup(InterfaceFunction.power), connectivity=parent,
            )
        return formfield


class ConnectivityForm(forms.ModelForm):
    pin_spreadsheet_input = forms.CharField(
        required=False,
        help_text="Paste pin data from a prepared spreadsheet here",
        widget=forms.Textarea(attrs={"rows": 20, "cols": 160}),
    )

    class Meta:
        model = Connectivity
        fields = [
            "name",
            "pin_spreadsheet_input",
            "simplified_connectivity",
        ]

    name = forms.CharField(widget=forms.TextInput(attrs={"size": 50}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        pin_spreadsheet_input = cleaned_data.get("pin_spreadsheet_input", None)

        # Validate spreadsheet inputs without committing them to the db.
        if pin_spreadsheet_input:
            process_connectivity_input(self.instance, pin_spreadsheet_input)

        return cleaned_data


@admin.register(Connectivity)
class ConnectivityAdmin(AutocompleteFilterMixin, BaseAdmin):
    form = ConnectivityForm
    search_fields = ["name"]
    list_display = [
        "name",
        "drawing",
        "is_simplified",
        "created",
        "updated",
    ]
    list_filter = [
        ("interfaces__interface_type", AutocompleteListFilter),
        "created",
        "updated",
        "created_by",
    ]
    inlines = [
        InterfaceInline,
        PinInline,
    ]
    fields = [
        "name",
        "large_drawing",
        "schematic_symbol",
        "simplified_connectivity",
        "created",
        "updated",
        "created_by",
    ]

    ordering = ["-created"]

    create_fields = ["name", "schematic_symbol", "simplified_connectivity"]
    autocomplete_fields = ["schematic_symbol"]
    readonly_fields = ["created", "updated", "created_by", "large_drawing"]
    save_on_top = True
    show_duplicate = True

    def get_fields(self, request, obj=None):
        """
        Hook for specifying fields.
        """
        if obj:
            fields = self.fields
        else:
            fields = self.create_fields

        if self.is_bulk_mode:
            return fields + ["pin_spreadsheet_input"]
        return fields

    def get_inline_instances(self, request, obj=None):
        if self.is_bulk_mode:
            return []
        return super().get_inline_instances(request, obj=obj)

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        self.is_bulk_mode = request.GET.get("bulk_edit", False)

        return super().changeform_view(
            request, object_id=object_id, form_url=form_url, extra_context=extra_context
        )

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        pin_spreadsheet_input = form.cleaned_data.get("pin_spreadsheet_input", None)
        if pin_spreadsheet_input:
            pin_data = process_connectivity_input(
                form.instance, pin_spreadsheet_input, commit=True
            )
        else:
            pin_data = {}

        # Generate the list of automatically assigned pins and send a message to the admin
        automatically_assigned = [
            f"{assignment.interface.name}.{assignment.interface_pin.reference}"
            for assignment in pin_data.get("automatic_assignments", [])
        ]

        if automatically_assigned:
            message = f'Automatically added assignments for the following pins: {", ".join(automatically_assigned)}.'
            messages.add_message(request, messages.WARNING, message)

    def is_simplified(self, obj):
        return "⚠️" if obj.simplified_connectivity else ""

    def drawing(self, obj, size=100, center=True):
#        url = reverse("connectivity_drawing", args=[obj.id])
        url = "localhost"
        alignment_style = "display: block; margin: auto;" if center else ""
        return mark_safe(
            f'<a href={url} target="_blank">'
            f'<img src={url} style="max-height: {size}px; max-width: {size}px; {alignment_style}"/></a>'
        )

    def large_drawing(self, obj):
        return self.drawing(obj, size=500, center=False)

    large_drawing.short_description = "Drawing"  # type: ignore
