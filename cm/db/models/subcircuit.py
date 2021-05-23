from copy import copy

from django.db.models import Manager

from .block import Block


class SubCircuitManager(Manager):
    def get_queryset(self):
        qs = super().get_queryset()
        return qs.filter(block_type=Block.BlockType.subcircuit)


class SubCircuit(Block):
    objects = SubCircuitManager()

    class Meta:
        verbose_name = "Sub-circuit"
        proxy = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.block_type = Block.BlockType.subcircuit

    def __str__(self):
        return self.name

    def duplicate(self):
        """Create a duplicate instance of this sub-circuit."""
        existing = SubCircuit.objects.get(pk=self.pk)
        duplicate_instance = copy(self)

        if duplicate_instance.name == existing.name:
            duplicate_instance.name += " (Copy)"

        duplicate_instance.pk = None
        duplicate_instance.save()

        # Add the existing object's categories to the duplicate
        for category in existing.categories.all():
            duplicate_instance.categories.add(category)

        # Duplicate buses (which will also duplicate filters)
        for bus in existing.bus_fragments.all():
            bus.duplicate(subcircuit_id=duplicate_instance.pk)

        return duplicate_instance
