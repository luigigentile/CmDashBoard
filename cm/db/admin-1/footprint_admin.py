from django.contrib import admin

from cm.db.models import Footprint

from .base_admin import BaseAdmin


@admin.register(Footprint)
class FootprintAdmin(BaseAdmin):
    search_fields = ["name", "category__name"]
    list_filter = ["category"]
    list_display = ["name", "category"]
    fields = ["name", "category", "source_file"]
