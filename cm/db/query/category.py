from typing import cast

from cm.db import constants, models


def controller_category() -> models.Category:
    return cast(
        models.Category, models.Category.objects.get(slug=constants.CONTROLLER_SLUG)
    )
