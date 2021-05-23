from django.contrib import admin

from cm.db.models import PinAssignment

from .base_admin import BaseAdmin


@admin.register(PinAssignment)
class PinAssignmentAdmin(BaseAdmin):
    search_fields = ["interface__name"]

    def get_search_results(self, request, queryset, search_term):
        queryset, use_distinct = super().get_search_results(
            request, queryset, search_term
        )
        return queryset, use_distinct
