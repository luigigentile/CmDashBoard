from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile
from django.utils.html import format_html
from mptt.admin import DraggableMPTTAdmin

from cm.db.models import AttributeDefinition, Category

from .base_admin import BaseAdmin, BaseTabularInline

VALID_SVG_MIME_TYPES = ["image/svg", "image/svg+xml", ""]


class AttributeDefinitionInline(BaseTabularInline):
    model = AttributeDefinition
    extra = 1
    exclude = ["interface_type", "block_attribute", "created_by"]


class CategoryForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["parent"].queryset = Category.objects.exclude(
                pk=self.instance.pk
            )

    def clean_icon(self):
        icon = self.cleaned_data["icon"]
        if icon and isinstance(icon, UploadedFile):
            content_type = icon.content_type
            if content_type not in VALID_SVG_MIME_TYPES:
                raise ValidationError(
                    f"Category icons should be SVG files! (Type was {content_type})"
                )
        return self.cleaned_data["icon"]


@admin.register(Category)
class CategoryAdmin(BaseAdmin, DraggableMPTTAdmin):
    prepopulated_fields = {"slug": ("label",)}
    form = CategoryForm
    search_fields = ["parent__label", "label"]
    fields = [
        "label",
        "slug",
        "icon",
        "parent",
        "reference_label",
        "background_color",
        "width",
        "height",
        "connector",
    ]
    # autocomplete_fields = ['parent']  # This breaks the tree display
    inlines = [AttributeDefinitionInline]

    list_display = ("tree_actions", "display_text")
    list_display_links = ("display_text",)

    def display_text(self, instance):
        disp_text = ""
        if instance.reference_label != "":
            disp_text = f"   [{instance.reference_label}]"

        return format_html(
            '<div style="text-indent:{}px">{}<font color="#000099">{}</font></div>',
            instance._mpttfield("level") * self.mptt_level_indent,
            instance.label,
            disp_text,
        )
