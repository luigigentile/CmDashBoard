from django.contrib import admin

from cm.db.models import Distributor

from .base_admin import BaseAdmin


@admin.register(Distributor)
class DistributorAdmin(BaseAdmin):
    search_fields = ["name"]
    fields = ["name", "skus_priced_on_same_scale"]
