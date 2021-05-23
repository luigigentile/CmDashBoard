from django import forms
from django.contrib import admin
from django.urls import reverse
from django.utils.html import mark_safe

from cm.db.models import BusFragment, Interface, InterfaceAdapter, InterfaceType

from .base_admin import BaseAdmin, BaseTabularInline


class BusFragmentForm(forms.ModelForm):
    class Meta:
        model = BusFragment
        fields = [
            "name",
            "from_filter",
            "from_interface_type",
            "from_interface",
            "to_filter",
            "to_interface_type",
            "to_interface",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["from_filter"].empty_label = "Sub-Circuit"
        self.fields["to_filter"].empty_label = "Sub-Circuit"

        if not self.instance or not self.instance.pk:
            # Filtering for interfaces only works when the bus fragment exists already.
            return

        def get_queryset(model, **kwargs):
            if any(kwargs.values()):
                return model.objects.filter(
                    **{key: value for key, value in kwargs.items() if value}
                )
            else:
                return model.objects.none()

        # From filter and to filter behave differently from the other querysets
        # If no bus fragment exists, that's because this is a "new bus fragment" row in the subcircuit admin.
        # In that case, we want to not filter the queryset, and let the inline admin filter it down, taking the parent
        # form's object into account.
        if self.instance.subcircuit_id:
            self.fields["from_filter"].queryset = self.fields[
                "from_filter"
            ].queryset.filter(subcircuit=self.instance.subcircuit_id)
            self.fields["to_filter"].queryset = self.fields[
                "to_filter"
            ].queryset.filter(subcircuit=self.instance.subcircuit_id)

        from_connectivity_id = (
            self.instance.from_filter.connectivity_id
            if self.instance.from_filter_id
            and self.instance.from_filter.connectivity_id
            else self.instance.subcircuit.connectivity_id
            if self.instance.subcircuit_id
            else None
        )
        self.fields["from_interface_type"].queryset = (
            InterfaceType.get_children(
                get_queryset(
                    InterfaceType, interfaces__connectivity_id=from_connectivity_id,
                ),
                include_self=True,
            )
            .distinct()
            .order_by("name")
        )
        self.fields["from_interface"].queryset = (
            get_queryset(
                Interface,
                connectivity_id=from_connectivity_id,
                interface_type__in=(
                    self.instance.from_interface_type.get_ancestors(include_self=True)
                    if self.instance.from_interface_type_id
                    else None
                ),
            )
            .distinct()
            .order_by("name")
        )

        to_connectivity_id = (
            self.instance.to_filter.connectivity_id
            if self.instance.to_filter_id and self.instance.to_filter.connectivity_id
            else self.instance.subcircuit.connectivity_id
            if self.instance.subcircuit_id
            else None
        )
        self.fields["to_interface_type"].queryset = (
            InterfaceType.get_children(
                get_queryset(
                    InterfaceType, interfaces__connectivity_id=to_connectivity_id
                ),
                include_self=True,
            )
            .distinct()
            .order_by("name")
        )
        self.fields["to_interface"].queryset = (
            get_queryset(
                Interface,
                connectivity_id=to_connectivity_id,
                interface_type__in=(
                    self.instance.to_interface_type.get_ancestors(include_self=True)
                    if self.instance.to_interface_type_id
                    else None
                ),
            )
            .distinct()
            .order_by("name")
        )


class InterfaceAdapterForm(forms.ModelForm):
    class Meta:
        model = InterfaceAdapter
        fields = ["original_from", "adapted_from", "original_to", "adapted_to"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # This field has to be blankable in the model, because we precreate these objects.
        # But a user should always have to fill in the "original_to" field, as that describes which field
        # maps to which.
        self.fields["original_to"].required = True


class InterfaceAdapterInline(BaseTabularInline):
    model = InterfaceAdapter
    form = InterfaceAdapterForm
    extra = 1
    fields = ["original_from", "adapted_from", "original_to", "adapted_to"]

    def formfield_callback(self, db_field, formfield, request, parent=None):
        if not parent:
            raise RuntimeError(
                "This form should only be used with an existing bus fragment!"
            )

        from_interface_type = (
            parent.from_interface_type or parent.from_interface.interface_type
        )
        to_interface_type = (
            parent.to_interface_type or parent.to_interface.interface_type
        )
        from_pins = formfield.queryset.filter(interface_type=from_interface_type)
        to_pins = formfield.queryset.filter(interface_type=to_interface_type)

        if db_field.name == "original_from":
            formfield.queryset = from_pins
        elif db_field.name == "original_to":
            formfield.queryset = to_pins
        elif db_field.name == "adapted_from":
            # Valid choices for adapting the from pin are the pins compatible with the possible to-pins
            formfield.queryset = formfield.queryset.filter(compatible_pins__in=to_pins)
        elif db_field.name == "adapted_to":
            # Valid choices for adapting the to pin are the pins compatible with the possible from-pins
            formfield.queryset = formfield.queryset.filter(
                compatible_pins__in=from_pins
            )
        return formfield


@admin.register(BusFragment)
class BusFragmentAdmin(BaseAdmin):
    form = BusFragmentForm
    readonly_fields = ["subcircuit_link"]
    inlines = [InterfaceAdapterInline]

    fieldsets = (
        (None, {"fields": ("name", "subcircuit_link"),}),
        ("From", {"fields": ("from_filter", "from_interface_type", "from_interface"),}),
        ("To", {"fields": ("to_filter", "to_interface_type", "to_interface"),}),
    )

    def subcircuit_link(self, instance):
        subcircuit = instance.subcircuit
        if not subcircuit:
            return "-"

        url = reverse(
            f"admin:{subcircuit._meta.app_label}_{subcircuit._meta.model_name}_change",
            args=[subcircuit.id],
        )

        return mark_safe(f'<a href="{url}" target="_blank">{subcircuit}</a>',)

    subcircuit_link.short_description = "Subcircuit"  # type: ignore
