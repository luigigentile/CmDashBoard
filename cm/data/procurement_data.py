"""Interface and data structures for fetching live information about parts from third-party APIs.

This can include prices, inventory, etc."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterator, List, Optional, cast
from uuid import UUID

from django.conf import settings

from cm.db import models
from cm.octopart.octopart_api import OctopartClient, OctopartLookup
from cm.optimization import types as optimization_types


class SKUType(Enum):
    tube = 1
    reel = 2


@dataclass
class DistributorPart:
    id: str
    part_number: str
    manufacturer_name: str
    distributor_name: str
    stock_keeping_units: List["StockKeepingUnit"]
    moq: int = field(default=1)
    mixing_allowed: bool = False

    @staticmethod
    def generate_id(manufacturer_name: str, part_number: str, distributor: str) -> str:
        """Geenerate a globally-unique ID for this distributor part."""
        return f"{manufacturer_name}/{part_number}/{distributor}"

    def to_optimization(
        self, buyable_block: optimization_types.PartProcurement
    ) -> optimization_types.DistributorPart:
        distributor_part = optimization_types.DistributorPart(
            id=self.id,
            buyable_block=buyable_block,
            moq=self.moq,
            part_number=self.part_number,
            distributor_name=self.distributor_name,
            stock_keeping_units=[],
        )
        distributor_part.stock_keeping_units = [
            stock_keeping_unit.to_optimization(distributor_part)
            for stock_keeping_unit in self.stock_keeping_units
        ]
        return distributor_part


@dataclass
class StockKeepingUnit:
    id: str
    type: SKUType
    price_brackets: List["PriceBracket"] = field(default_factory=list)
    increment_inventories: Dict[int, int] = field(
        default_factory=dict
    )  # key: increment, value: inventory left.

    packaging: Optional[str] = field(default=None, repr=False)

    @staticmethod
    def generate_id(
        manufacturer_name: str, part_number: str, distributor: str, identifier: str
    ) -> str:
        """Geenerate a globally-unique ID for this SKU.

        `identifier` is the identifier used for this SKU by the manufacturer, and generally not globally unique.

        Note: our understanding of a SKU doesn't necessarily match a distributor's! We will sometimes combine
        multiple SKU's of a distributor into a single SKU in our side, in which case identifier will be a combination
        of identifiers on the distributor side.
        """
        return f"{manufacturer_name}/{part_number}/{distributor}/{identifier}"

    def to_optimization(
        self, distributor_part: optimization_types.DistributorPart
    ) -> optimization_types.StockKeepingUnit:
        stock_keeping_unit = optimization_types.StockKeepingUnit(
            id=self.id,
            distributor_part=distributor_part,
            price_brackets=[],
            increments=[],
        )
        stock_keeping_unit.price_brackets = [
            optimization_types.PriceBracket(
                unit_price=price_bracket.unit_price,
                quantity_min=price_bracket.quantity_min,
                quantity_max=price_bracket.quantity_max or 1000000000,
                stock_keeping_unit=stock_keeping_unit,
            )
            for price_bracket in self.price_brackets
        ]
        stock_keeping_unit.increments = [
            optimization_types.Increment(
                value=value,
                increment_type=optimization_types.IncrementType(self.type.value),
                stock_keeping_unit=stock_keeping_unit,
            )
            for value in self.increment_inventories.keys()
        ]
        return stock_keeping_unit


@dataclass
class PriceBracket:
    quantity_min: int
    unit_price: float
    quantity_max: Optional[int] = None


def _parse_octopart_sku_type(octopart_packaging_data: Optional[str]) -> SKUType:
    if not octopart_packaging_data:
        return SKUType.tube

    return SKUType.reel if octopart_packaging_data.lower() == "reel" else SKUType.tube


def _get_moq(offer: Dict[str, Any]) -> int:
    """
    MOQ is, for some reason, optional in the octopart API
    This function tries getting the moq from an offer
    and provides a fallback to the lowest quantity if moq is none
    """
    return cast(
        int,
        offer["moq"]
        or (
            sorted(offer["prices"], key=lambda u: u["quantity"])[0]["quantity"]
            if len(offer["prices"])
            else 1
        ),
    )


def _octopart_part_to_distributor_parts(
    octopart_part: Dict[str, Any],
    manufacturer: str,
    part_number: str,
    all_distributor_settings: Dict[str, Dict[str, Any]],
) -> Iterator[DistributorPart]:
    """Turns the raw octopart parts into distributor part objects."""
    for seller in octopart_part["sellers"]:
        distributor_name = seller["company"]["name"]
        distributor_settings = all_distributor_settings[distributor_name]

        distributor_part = DistributorPart(
            id=DistributorPart.generate_id(manufacturer, part_number, distributor_name),
            part_number=part_number,
            manufacturer_name=manufacturer,
            distributor_name=seller["company"]["name"],
            # MOQ is, for some reason, optional in the octopart API
            moq=min(_get_moq(offer) for offer in seller["offers"]),
            stock_keeping_units=[],
        )

        if distributor_settings["skus_on_same_scale"]:
            # If skus are all priced together, we only create a single SKU
            offers = [
                {
                    "prices": sorted(
                        [
                            price
                            for offer in seller["offers"]
                            for price in offer["prices"]
                        ],
                        key=lambda u: u["quantity"],
                    ),
                    "sku_type": SKUType.tube,  # TODO handle SKUType for mixed SKUs
                    "packaging": seller["offers"][0]["packaging"],
                    "inventories": {
                        _get_moq(offer): offer["inventory_level"]
                        for offer in seller["offers"]
                    },
                    # We're combining several SKUs into one, reflect that in the local identifier
                    "identifier": "|".join(offer["id"] for offer in seller["offers"]),
                }
            ]
        else:
            # Otherwise create separate SKUs
            offers = [
                {
                    "prices": sorted(offer["prices"], key=lambda u: u["quantity"]),
                    "sku_type": _parse_octopart_sku_type(offer["packaging"]),
                    "packaging": offer["packaging"],
                    "inventories": {_get_moq(offer): offer["inventory_level"]},
                    "identifier": offer["id"],
                }
                for offer in seller["offers"]
            ]

        for offer in offers:
            # Filter out offers that have no prices
            if not offer["prices"]:
                continue

            sku = StockKeepingUnit(
                id=StockKeepingUnit.generate_id(
                    manufacturer, part_number, distributor_name, offer["identifier"]
                ),
                increment_inventories=offer["inventories"],
                type=offer["sku_type"],
                price_brackets=[
                    PriceBracket(
                        quantity_min=price_bracket["quantity"],
                        quantity_max=offer["prices"][i + 1]["quantity"]
                        if i + 1 < len(offer["prices"])
                        else None,
                        unit_price=price_bracket["converted_price"],
                    )
                    for i, price_bracket in enumerate(offer["prices"])
                    if price_bracket["converted_currency"]
                    == settings.OCTOPART_CURRENCY  # Ignore prices not in the required currency
                ],
            )
            distributor_part.stock_keeping_units.append(sku)

        yield distributor_part


def _distributor_settings(distributor_name: str) -> Dict[str, Any]:
    """Return the settings we use for a distributor."""
    distributor = models.Distributor.objects.filter(name=distributor_name).first()

    return {
        "skus_on_same_scale": distributor.skus_priced_on_same_scale
        if distributor
        else False
    }


def _get_data(
    manufacturer_parts: List[models.ManufacturerPart],
) -> Dict[UUID, List[DistributorPart]]:
    """Fetch raw procurement data from cache/third-party APIs and return them as distributor parts."""

    # This is currently hardcoded to just use octopart - in the future we might want to generalise this
    # and allow multiple data sources.
    octopart_client = OctopartClient(
        settings.OCTOPART_API_TOKEN,
        settings.REDIS_URL,
        settings.OCTOPART_CACHE_REDIS_DB,
        settings.OCTOPART_CACHE_EXPIRY,
    )

    lookups = {
        manufacturer_part.id: OctopartLookup(
            mpn=manufacturer_part.part_number,
            manufacturer=manufacturer_part.manufacturer.name,
        )
        for manufacturer_part in manufacturer_parts
    }

    raw_data = octopart_client.lookup_parts(lookups)
    all_distributor_settings: Dict[str, Dict[str, Any]] = {}

    # Iterate the data once to get all required distributors, avoided repeated db lookups
    for octopart_part in raw_data.values():
        if not octopart_part:
            continue
        for seller in octopart_part["sellers"]:
            distributor_name = seller["company"]["name"]
            if distributor_name not in all_distributor_settings:
                all_distributor_settings[distributor_name] = _distributor_settings(
                    distributor_name
                )

    result: Dict[UUID, List[DistributorPart]] = {}
    for manufacturer_part_id, octopart_part in raw_data.items():
        if not octopart_part:
            result[manufacturer_part_id] = []
            continue
        result[manufacturer_part_id] = list(
            _octopart_part_to_distributor_parts(
                octopart_part,
                manufacturer=lookups[manufacturer_part_id].manufacturer,
                part_number=lookups[manufacturer_part_id].mpn,
                all_distributor_settings=all_distributor_settings,
            )
        )
    return result


def get_procurement_data(
    manufacturer_part: models.ManufacturerPart,
) -> List[DistributorPart]:
    """Fetch procurement data for a single manufacturer part.

    Returns a list of DistributorPart objects with information about the part for each distributor
    that has it available."""
    return _get_data([manufacturer_part])[manufacturer_part.id]


def bulk_get_procurement_data(
    manufacturer_parts: List[models.ManufacturerPart],
) -> Dict[UUID, List[DistributorPart]]:
    """Like procurement_data, but fetches distributor parts for multiple manufacturer parts more efficiently at once."""
    return _get_data(manufacturer_parts)
