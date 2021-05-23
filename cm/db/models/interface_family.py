from cm.db.fields import SmallTextField

from .base_model import BaseModel


class InterfaceFamily(BaseModel):
    """An interface family is a loose grouping of interfaces that have some mutual compatibility.

    Two interfaces types with the same family aren't necessarily always compatible, but they are based on
    the same technology/protocol. Examples of interface families are
        SPI (containing any SPI variant)
        two-wire (containing TWI, I2c, SMBus)
    """

    class Meta:
        verbose_name_plural = "Interface Families"

    name = SmallTextField(help_text="Human-readable name for this family")
    label = SmallTextField(help_text="Label for this family, used in the software")

    def __str__(self) -> str:
        return self.name
