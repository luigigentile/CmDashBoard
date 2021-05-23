from django.contrib import admin

from cm.db.admin.base_admin import BaseAdmin


from cm.db.models import (
    Block,
)

@admin.register(Block)
class BlockAdmin(BaseAdmin):
    model = Block
    fields = ["name", "description"]
  


