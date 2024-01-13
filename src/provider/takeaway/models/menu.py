from dataclasses import dataclass
from enum import auto
from typing import Self, Tuple

from provider.takeaway.models.common import (
    IdEnum,
    ShippingType,
    DeliveryTimeframesDay,
    Weekday,
)


@dataclass
class OptionPrices:
    delivery: float | None
    pickup: float | None
    deposit: float | None

    @classmethod
    def from_dict(cls, d: dict) -> Self:
        return cls(
            d["delivery"],
            d["pickup"],
            d["deposit"],
        )


class OptionMetricUnit(IdEnum):
    ml = auto()
    g = auto()


@dataclass
class OptionMetric:
    unit: str
    quantity: int | None

    @classmethod
    def from_dict(cls, d: dict) -> Self:
        return cls(d["unit"], int(d["quantity"]) if d["quantity"] else None)


@dataclass
class Option:
    id: str
    name: str
    min_amount: int
    max_amount: int
    prices: OptionPrices
    metric: OptionMetric
    price_unit: str | None
    price_per_unit_pickup: int | None
    price_per_unit_delivery: int | None
    alcohol_volume: float | None
    caffeine_amount: float | None
    is_sold_out: bool
    is_excluded_from_mov: bool  # mov?

    @classmethod
    def from_item(cls, item: Tuple[str, dict]) -> Self:
        _id, d = item

        return cls(
            _id,
            d["name"],
            d["minAmount"],
            d["maxAmount"],
            OptionPrices.from_dict(d["prices"]),
            OptionMetric.from_dict(d["metric"]),
            d["priceUnit"],
            int(d["pricePerUnitPickup"]) if d["pricePerUnitPickup"] else None,
            int(d["pricePerUnitDelivery"]) if d["pricePerUnitDelivery"] else None,
            float(d["alcoholVolume"].replace(",", ".")) if d["alcoholVolume"] else None,
            float(d["caffeineAmount"].replace(",", ".")) if d["caffeineAmount"] else None,
            d["isSoldOut"],
            d["isExcludedFromMov"],
        )


@dataclass
class OptionGroup:
    id: str
    name: str
    is_type_multi: bool
    is_required: bool
    min_choices: int
    max_choices: int
    options: list[Option]

    @classmethod
    def from_item(cls, item: Tuple[str, dict], options: list[Option]) -> Self:
        _id, d = item
        return cls(
            _id,
            d["name"],
            d["isTypeMulti"],
            d["isRequired"],
            d["minChoices"],
            d["maxChoices"],
            [option for option in options if option.id in d["optionIds"]],
        )


class PriceUnit(IdEnum):
    liter = auto()
    kilogram = auto()


@dataclass
class Variant:
    id: str
    name: str
    option_groups: list[OptionGroup]
    shipping_types: list[ShippingType]
    prices: OptionPrices
    metric: OptionMetric
    price_unit: PriceUnit | None
    price_per_unit_pickup: int | None
    price_per_unit_delivery: int | None
    alcohol_volume: float | None
    caffeine_amount: float | None
    is_sold_out: bool
    is_excluded_from_mov: bool  # mov?

    @classmethod
    def from_dict(cls, d: dict, option_groups: list[OptionGroup]) -> Self:
        return cls(
            d["id"],
            d["name"],
            [option_group for option_group in option_groups if option_group in d["optionGroupIds"]],
            [ShippingType.from_key(s) for s in d["shippingTypes"]],
            OptionPrices.from_dict(d["prices"]),
            OptionMetric.from_dict(d["metric"]),
            d["priceUnit"],
            int(d["pricePerUnitPickup"]) if d["pricePerUnitPickup"] else None,
            int(d["pricePerUnitDelivery"]) if d["pricePerUnitDelivery"] else None,
            float(d["alcoholVolume"].replace(",", ".")) if d["alcoholVolume"] else None,
            float(d["caffeineAmount"].replace(",", ".")) if d["caffeineAmount"] else None,
            d["isSoldOut"],
            d["isExcludedFromMov"],
        )


@dataclass
class Product:
    id: str
    name: str
    description: list[str]
    image_url: str | None
    variants: list[Variant]

    @classmethod
    def from_item(cls, item: Tuple[str, dict], option_groups: list[OptionGroup]) -> Self:
        _id, d = item
        return cls(
            _id,
            d["name"],
            d["description"],
            d["imageUrl"],
            [Variant.from_dict(v, option_groups) for v in d["variants"]],
        )


@dataclass
class Category:
    id: str
    name: str
    imageUrl: str | None
    overview_image_url: str | None
    time_restrictions: list[DeliveryTimeframesDay]
    products: list[Product]

    @classmethod
    def from_dict(cls, d: dict, products: list[Product]) -> Self:
        image_url = d["imageUrl"] if d["imageUrl"] else d["imageUrl"]

        time_restrictions = []
        for time_restriction in d.get("timeRestrictions", {}).items():
            try:
                time_restrictions.append(DeliveryTimeframesDay.from_item(time_restriction))
            except IndexError:
                pass

        return cls(
            d["id"],
            d["name"],
            image_url,
            d["overviewImageUrl"],
            time_restrictions,
            [product for product in products if product.id in d["productIds"]],
        )


class CurrencyCode(IdEnum):
    EUR = auto()


@dataclass
class Currency:
    demoninator: int
    code: CurrencyCode

    @classmethod
    def from_dict(cls, d: dict) -> Self:
        return cls(int(d["demoninator"]), CurrencyCode.from_key(d["currencyCode"]))


class DiscountType(IdEnum):
    product = auto()
    Order = auto()
    NthProduct = auto()
    combination = auto()

    @classmethod
    def from_key(cls, s: str):
        if s.lower() == "nth-product":
            return DiscountType.NthProduct

        return super().__init__(s)


@dataclass
class Discount:
    type: DiscountType
    name: str
    description: str
    day_of_week: Weekday | None
    promotion_price: int | None
    absolute_amount: int | None
    percentage_amount: int | None
    are_side_dishes_included: bool
    is_applied_to_every_occurrence: bool
    nth_occurrence: None
    start_from_amount: None  # | int?
    shipping_types: list[ShippingType]
    product_groups: list[list[str]]

    @classmethod
    def from_dict(cls, d: dict) -> Self:
        return cls(
            DiscountType.from_key(d["type"]),
            d["name"],
            d["description"],
            Weekday(d["dayOfWeek"]) if d["dayOfWeek"] else None,
            int(d["promotionPrice"]) if d["promotionPrice"] else None,
            int(d["absoluteAmount"]) if d["absoluteAmount"] else None,
            int(d["percentageAmount"]) if d["percentageAmount"] else None,
            d["areSideDishesIncluded"],
            d["isAppliedToEveryOccurrence"],
            d["nthOccurrence"],
            d["startFromAmount"],
            [ShippingType.from_key(s) for s in d["shippingTypes"]],
            d["productGroups"],
        )


@dataclass
class Menu:
    currency: Currency
    categories: list[Category]
    option_groups: list[OptionGroup]
    options: list[Option]
    products: list[Product]
    popular_products: list[Product]
    discounts: list[Discount]
    auto_added_products: dict

    @classmethod
    def from_dict(cls, d: dict) -> Self:
        options = [Option.from_item(o) for o in d["options"].items()]
        option_groups = [OptionGroup.from_item(o, options) for o in d["optionGroups"].items()]
        products = [Product.from_item(p, option_groups) for p in d["products"].items()]
        popular_products = [product for product in products if product.id in d["popularProductIds"]]

        return cls(
            d["currency"],
            [Category.from_dict(c, products) for c in d["categories"]],
            option_groups,
            options,
            products,
            popular_products,
            [Discount.from_dict(di) for di in d["discounts"]],
            d["autoAddedProducts"],
        )
