from django import forms
from django.contrib import admin
from django.contrib.admin.widgets import FilteredSelectMultiple

from cm.db.constants import AncillaryAppliesTo
from cm.db.models import Ancillary, InterfaceFamily, InterfaceType

from .ancillary_admin import AncillaryInlineBaseForm
from .base_admin import BaseAdmin, BaseTabularInline


class InterfaceFamilyForm(forms.ModelForm):
    class Meta:
        model = InterfaceFamily
        fields = ["name", "label"]

    interface_types = forms.ModelMultipleChoiceField(
        queryset=InterfaceType.objects.all(),
        widget=FilteredSelectMultiple(verbose_name="interface_types", is_stacked=False),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance:
            self.fields["interface_types"].initial = self.instance.interface_types.all()


class AncillaryInline(BaseTabularInline):
    form = AncillaryInlineBaseForm
    model = Ancillary
    exclude = ["interface"]
    extra = 1
    show_change_link = True

    def formfield_callback(self, db_field, formfield, request, parent=None):
        if db_field.name == "applies_to":
            # Interface families only allow configuring bus ancillaries
            db_field.choices = [
                (
                    AncillaryAppliesTo.bus,
                    AncillaryAppliesTo.labels[AncillaryAppliesTo.bus],
                )
            ]
            db_field.default = AncillaryAppliesTo.bus
        return formfield


@admin.register(InterfaceFamily)
class InterfaceFamilyAdmin(BaseAdmin):
    form = InterfaceFamilyForm
    list_display = ["name", "label", "interface_types"]

    def save_model(self, request, obj, form, change):
        new_interface_types = form.cleaned_data["interface_types"]
        obj.interface_types.set(new_interface_types)
        obj.save()

    def get_inlines(self, request, obj=None):
        if obj:
            # Only show ancillary inline when editing families, not when creating new ones.
            return [AncillaryInline]
        else:
            return []

    def interface_types(self, obj):
        return ", ".join(t.name for t in obj.interface_types.all())
