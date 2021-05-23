from django.core.exceptions import ValidationError
from django.db import models
from djchoices import ChoiceItem, DjangoChoices

from cm.db.fields import SmallTextField

from .base_model import BaseModel


class ConnectionRule(BaseModel):
    """A ConnectionRule defines how an interface should connect to other interfaces in the circuit.

    The rule uses a filter to determine which kinds of components are valid for a given connection. For now, these
    are hardcoded, for example the "microcontroller" filter might be implemented in code as "any component in the
    microcontroller category". In the future, these filters might become user-configurable.

    The rule's priority decides which rule should be used for a given interface - for now this won't apply and the
    rule with the lowest priority number will always be used.
    """

    class Meta:
        ordering = ("priority", "id")

    class FixedComponentFilter(DjangoChoices):
        """Represents a fixed filter for components, hardcoded in our own code.

        In the future connection rules might offer more flexibility to let users define custom logic to decide
        which components to connect to, but for now we limit ourselves to some very simple fixed rules.
        """

        microcontroller = ChoiceItem("microcontroller", "Connect to Microcontroller")
        vref = ChoiceItem("vref", "Connect to reference Voltage")
        gnd = ChoiceItem("gnd", "Connect to GND (of the reference voltage)")

    # Rules always apply to interfaces, but they can be defined on an interface type as a shortcut for creating them
    # on all interfaces of that type.
    interface_type = models.ForeignKey(
        "db.InterfaceType",
        on_delete=models.PROTECT,
        related_name="connection_rules",
        null=True,
        blank=True,
    )
    interface = models.ForeignKey(
        "db.Interface",
        on_delete=models.PROTECT,
        related_name="connection_rules",
        null=True,
        blank=True,
    )

    priority = models.PositiveIntegerField(
        default=10, help_text="Priority - lower number is higher priority."
    )
    component_filter = SmallTextField(choices=FixedComponentFilter.choices)

    def clean(self):
        if not self.interface_type_id and not self.interface_id:
            raise ValidationError(
                "A connection rule has to have an interface or an interface type!"
            )
        if self.interface_type_id and self.interface_id:
            raise ValidationError(
                "A connection rule has to have either an interface or an interface type, not both!"
            )

    def __str__(self):
        return f"{self.FixedComponentFilter.labels[self.component_filter]} ({self.priority})"
