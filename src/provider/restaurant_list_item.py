import re
from dataclasses import dataclass
from typing import Self

from provider.brand import BrandItem
from provider.common import (
    Indicator,
    Rating,
    Location,
    PaymentMethod,
    SupportOption,
    to_pascal_case,
    ShippingInfo,
)


@dataclass
class CuisineType:
    id: str

    def name(self) -> str | None:
        if re.search(r"^(\d+)$", self.id):
            # int values (e.g. 2600) aren't shown on the webpage/app either
            # we're just gonna ignore them (for now?)
            return None
        elif value := re.search(r"(.+?)_\d+", self.id):
            _name = value.group(1).replace("-", " ")
            return to_pascal_case(_name)

        return self.id

    @classmethod
    def from_dict(cls, s: str) -> Self:
        return cls(s)


@dataclass
class RestaurantListItem:
    id: str
    primary_slug: str
    indicators: list[Indicator]
    price_range: int
    popularity: int
    brand: BrandItem
    cuisine_types: list[CuisineType]
    rating: Rating
    location: Location
    supports: list[SupportOption]
    shipping_infos: list[ShippingInfo]
    payment_methods: list[PaymentMethod]

    @classmethod
    def from_dict(cls, d: dict) -> Self:
        indicators = [Indicator.from_key(s) for s in d["indicators"]]
        brand = BrandItem.from_dict(d["brand"])
        cuisine_types = [CuisineType.from_dict(c) for c in d["cuisineTypes"]]
        rating = Rating.from_dict(d["rating"])
        location = Location.from_dict(d["location"])
        supports = [SupportOption.from_key(s) for s in d["supports"]]
        shipping_infos = [ShippingInfo.from_dict(s) for s in d["shippingInfo"].items()]
        payment_methods = [PaymentMethod.from_key(s) for s in d["paymentMethods"]]

        return cls(
            d["id"],
            d["primarySlug"],
            indicators,
            d["priceRange"],
            d["popularity"],
            brand,
            cuisine_types,
            rating,
            location,
            supports,
            shipping_infos,
            payment_methods,
        )

    def offers_delivery(self) -> bool:
        return any(info.is_delivery_info() for info in self.shipping_infos)

    def delivery_info(self) -> ShippingInfo | None:
        if self.offers_delivery():
            return [info for info in self.shipping_infos if info.is_delivery_info()][0]

        return None

    def __hash__(self):
        return hash(self.id)
