from cm.db.admin.base_admin import BaseTabularInline
from cm.db.models import FilterQuery


class BaseFilterQueryInline(BaseTabularInline):
    model = FilterQuery
    extra = 1
    fields = ["attribute_definition", "operator", "value"]
