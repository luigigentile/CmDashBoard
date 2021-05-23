from django.contrib import admin

from cm.db.models import Manufacturer

from .base_admin import BaseAdmin


@admin.register(Manufacturer)
class ManufacturerAdmin(BaseAdmin):
    fields = ["name"]
    search_fields = ["name"]
