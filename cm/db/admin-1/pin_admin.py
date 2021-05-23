from django import forms
from django.contrib import admin

from cm.db.constants import PinType
from cm.db.models import Pin

from .base_admin import BaseAdmin


class PinForm(forms.ModelForm):
    class Meta:
        model = Pin
        fields = ["name", "number", "pin_type", "voltage_reference"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Filtering for pins of the same connectivity only works when the pin exists already.
        if not self.instance or not self.instance.pk:
            return

        if self.instance.connectivity_id:
            self.fields["voltage_reference"].queryset = Pin.objects.filter(
                connectivity_id=self.instance.connectivity_id, pin_type=PinType.power
            )


@admin.register(Pin)
class PinAdmin(BaseAdmin):
    form = PinForm
    search_fields = ["name", "number"]
    fields = ["name", "number", "pin_type", "voltage_reference", "ground_reference"]
    readonly_fields = ["ground_reference"]

    def ground_reference(self, obj):
        return obj.gnd_reference_pin()
