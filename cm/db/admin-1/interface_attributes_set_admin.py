from django.core.exceptions import ValidationError
from django.forms import BaseInlineFormSet, ModelForm

from cm.db.models import InterfaceAttributesSet, InterfaceType

from .base_admin import BaseTabularInline


class InterfaceAttributesSetForm(ModelForm):
    class Meta:
        model = InterfaceAttributesSet
        fields = ["interface_type", "interfaces", "attributes"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            interface_type = self.instance.interface_type
        except InterfaceType.DoesNotExist:
            pass
        else:
            self.fields["interfaces"].queryset = self.fields[
                "interfaces"
            ].queryset.filter(interface_type=interface_type)

    def clean(self):
        """Validate all interfaces are of the specified interface type."""
        super().clean()

        if "interface_type" in self.cleaned_data and any(
            interface.interface_type_id != self.cleaned_data["interface_type"].id
            for interface in self.cleaned_data["interfaces"]
        ):
            self.add_error(
                "interfaces",
                ValidationError(
                    "Interfaces must be of the requested interface type", code="invalid"
                ),
            )


class InterfaceAttributesSetFormSet(BaseInlineFormSet):
    def clean(self):
        """Validate interfaces are only used on one interface attributes set."""
        super().clean()

        # Get forms and interface sets for validation
        validation_data = [
            (form, set(form.cleaned_data["interfaces"]))
            for form in self.forms
            if "interfaces" in form.cleaned_data
            and form.cleaned_data["DELETE"] is False
        ]

        # For each form check that none of its interfaces are also selected on another form
        # FIXME: This algorithm is O(n2)
        for form, interfaces in validation_data:
            for other_form, other_interfaces in validation_data:
                if other_form == form:
                    continue
                if len(interfaces & other_interfaces) > 0:
                    form.add_error(
                        "interfaces",
                        ValidationError(
                            "Interfaces may only be used on one interface attributes set",
                            code="invalid",
                        ),
                    )


class InterfaceAttributesSetInline(BaseTabularInline):
    model = InterfaceAttributesSet
    form = InterfaceAttributesSetForm
    formset = InterfaceAttributesSetFormSet
    extra = 1
    verbose_name = "Interface Attributes"
    verbose_name_plural = "Interface Attributes"

    def formfield_callback(self, db_field, formfield, request, parent=None):
        if parent and parent.connectivity:
            if db_field.name == "interface_type":
                formfield.queryset = InterfaceType.objects.filter(
                    id__in=parent.connectivity.interfaces.values_list(
                        "interface_type_id", flat=True
                    )
                ).distinct()
            elif db_field.name == "interfaces":
                formfield.queryset = parent.connectivity.interfaces
        return formfield
