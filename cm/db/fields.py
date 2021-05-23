from django.db import models


class SmallTextField(models.TextField):
    """A simple override of TextField to allow specifying a text input widget in forms."""

    pass
