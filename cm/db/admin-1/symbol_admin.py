from django.contrib import admin

from cm.db.models import SchematicSymbol

from .base_admin import BaseAdmin


@admin.register(SchematicSymbol)
class SymbolAdmin(BaseAdmin):
    search_fields = ["name", "category__name"]
    list_filter = ["category"]
    list_display = ["name", "category"]
