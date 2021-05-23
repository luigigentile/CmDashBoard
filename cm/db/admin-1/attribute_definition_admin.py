from django import forms
from django.contrib import admin

from cm.db.models.attribute_definition import (
    AttributeDefinition,
    DirectAttributeDefinition,
)

from .base_admin import BaseAdmin


@admin.register(AttributeDefinition)
class AttributeDefinitionAdmin(BaseAdmin):
    search_fields = ["name", "unit"]
    list_filter = ["unit"]
    list_display = ["name", "unit"]


class DirectAttributeForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["block_attribute"].required = True


@admin.register(DirectAttributeDefinition)
class DirectAttributeDefinitionAdmin(BaseAdmin):
    search_fields = ["name", "datatype", "block_filter"]
    list_display = ["name", "block_attribute", "datatype"]
    form = DirectAttributeForm

    fields = [
        "name",
        "block_attribute",
        "datatype",
        "choices",
        "is_required",
    ]
