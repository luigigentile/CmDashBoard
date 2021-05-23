import uuid

from django.conf import settings
from django.db import models


class BaseModel(models.Model):
    class Meta:
        abstract = True

    id = models.UUIDField(primary_key=True, editable=False, default=uuid.uuid4)
    objects = models.Manager()

    created = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated = models.DateTimeField(auto_now=True, null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True
    )

    def save(self, *args, **kwargs):
        # Always run a full clean on save - this might turn out to be a bad idea.
        self.full_clean()
        return super().save(*args, **kwargs)
