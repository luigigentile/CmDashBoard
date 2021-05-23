from django.contrib import admin

from cm.db.models import InterfacePin

from .base_admin import BaseAdmin


@admin.register(InterfacePin)
class InterfacePinAdmin(BaseAdmin):
    search_fields = [
        "interface_type__name",
        "reference",
        "pin_type",
        "sharing",
        "description",
    ]
