from copy import copy

from django.db.models import Manager

from .block import Block


class PartManager(Manager):
    def get_queryset(self):
        qs = super().get_queryset()
        return qs.filter(block_type=Block.BlockType.part)


class Part(Block):
    objects = PartManager()

    class Meta:
        proxy = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.block_type = Block.BlockType.part

    def __str__(self):
        return self.name

    @property
    def is_connector(self):
        return self.categories.filter(connector=True).exists()

    def duplicate(self):
        """Create a duplicate instance of this part."""
        existing = Part.objects.get(pk=self.pk)
        duplicate_instance = copy(self)

        if duplicate_instance.name == existing.name:
            duplicate_instance.name += " (Copy)"

        duplicate_instance.pk = None
        duplicate_instance.save()

        # Add the existing object's categories to the duplicate
        for category in existing.categories.all():
            duplicate_instance.categories.add(category)

        return duplicate_instance
