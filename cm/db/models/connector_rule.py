from itertools import permutations
from typing import Iterator, NamedTuple, Optional

from django.db.models import QuerySet

from cm.db.fields import SmallTextField
from cm.db.models.base_model import BaseModel
from cm.db.models.block import Block
from cm.db.query.attribute import AttributeQuery


class ConnectorRule(BaseModel):
    """Two sets of rule queries ("from_queries" and "to_queries")
    that must be satisfied for two connectors to be compatible.

    When a compatible connector must be found all rules are evaluated
    to produce Django ORM filters using the following logic:
    * If one side of the rule matches the connector then the other side
      is added to the list of filters that compatible connectors must match
    * If one side of the rule does _not_ match the connector then the other
      side is added to the list of filters that compatible connectors
      must _not_ match

    For example, if a rule is defined such that:
    * FROM: gender = "male"
    * TO: gender = "female"

    Then when a compatible connector is needed for a "male" connector the
    rule will evaluate to:
    * INCLUDE: gender = "female"
    * EXCLUDE: gender = "male"

    However, if a compatible connector is needed for a connector without a
    gender set the rule will evaluate to:
    * INCLUDE: None
    * EXCLUDE: gender = "male", gender = "female"

    The use of "from" and "to" is arbitary as the rules are evaluated in both
    directions (and are thus symmetric).
    """

    class Filters(NamedTuple):
        include: Optional["QuerySet"] = None
        exclude: Optional["QuerySet"] = None

    name = SmallTextField(unique=True)

    def __str__(self):
        return self.name

    def filters(self, connector: Block) -> Iterator[Filters]:
        """Get a filter query of the "reverse" filter queries for
        this rule that match the specified connector."""

        # Get a queryset containing only the connector we are searching
        # for compatibility with
        qs = Block.objects.filter(id=connector.id)

        from_queryset = qs.filter(
            *[AttributeQuery.from_db(query).lookup for query in self.from_queries.all()]
        )
        to_queryset = qs.filter(
            *[AttributeQuery.from_db(query).lookup for query in self.to_queries.all()]
        )

        # Iterate through both permutations of filter querysets (i.e. from/to and to/from)
        # so that this rule is symmetric
        for queryset_a, queryset_b in permutations([from_queryset, to_queryset], 2):
            # If the connector is in the "from" queryset then compatible connectors
            # are in the "to" set
            if queryset_a.exists():
                yield self.Filters(include=queryset_b)

            # If the connector is NOT in the "to" queryset then compatible connectors
            # are NOT in the from queryset
            if not queryset_b.exists():
                yield self.Filters(exclude=queryset_a)

    @classmethod
    def compatible_connectors(cls, connector: Optional[Block]) -> QuerySet:
        """Get a queryset of compatible connectors for the give connector (if any)."""
        includes = []
        excludes = []

        if connector:
            rules = cls.objects.prefetch_related("from_queries", "to_queries")
            for rule in rules.all():
                for filters in rule.filters(connector):
                    if filters.include:
                        includes.append(filters.include)
                    if filters.exclude:
                        excludes.append(filters.exclude)

        # Note: this bypasses the usual query.blocks method, because connectors are not limited to a single
        # parent category. Any category can be a connector one, as long as it has the "connector" flag set.
        # We also have to make two queries out of this,
        # because intersection/different cannot be combined with additional filters.
        block_ids = (
            Block.objects.filter(categories__connector=True)
            .intersection(*includes)
            .difference(*excludes)
        ).values_list("id", flat=True)
        return Block.objects.filter(id__in=block_ids)
