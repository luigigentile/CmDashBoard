from typing import Any, List

from django.db.models import QuerySet

from cm.db import models

from .attribute import AttributeQuery


def blocks(
    category: models.Category,
    attribute_queries: List[AttributeQuery] = None,
    **lookups: Any
) -> QuerySet:
    """Standard interface for querying for blocks from the database.

    This captures the standard use case of getting a block from the database which
    - is part of a category (or its subcategories)
    - optionally has a number of attribute filters applied to it
    - optionally has some extra database filters.

    Almost any piece of code that queries for blocks should use this function, only bypass it
    if there's a specific use case that requires it. Connectors for example don't have a common
    category but are instead any category can be marked as a connector one with a flag.
    """
    attribute_queries = attribute_queries or []
    queryset = models.Block.objects.filter(
        categories__id__in=category.get_descendants(include_self=True).values_list(
            "id", flat=True
        ),
        **lookups
    )

    # Add lookups from attribute queries to the queryset
    for attribute_query in attribute_queries:
        queryset = queryset.filter(attribute_query.lookup)

    return queryset
