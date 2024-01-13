import inspect
from dataclasses import dataclass
from datetime import datetime
from typing import Tuple, Self
from zoneinfo import ZoneInfo

import httpx

from provider.brand import Brand
from provider.colophone import Colophon
from provider.common import (
    escape_markdown,
    DeliveryTimeframesDay,
    Rating,
    Location,
    SupportOption,
    Indicator,
    ShippingInfo,
)
from provider.logger import create_logger
from provider.menu import Menu
from provider.payment import Payment
from provider.restaurant_list_item import RestaurantListItem


@dataclass
class Summary:
    title: str | None
    content: str | None

    @classmethod
    def from_dict(cls, d: dict) -> Self:
        return cls(
            d["title"],
            d["content"],
        )


@dataclass
class Delivery:
    times: list[DeliveryTimeframesDay]
    is_open_for_order: bool
    is_open_for_preorder: bool
    is_scoober_restaurant: bool
    duration_range: Tuple[int, int] | None

    @classmethod
    def from_dict(cls, d: dict) -> Self:
        duration_range: Tuple[int, int] | None
        try:
            duration_range = (
                int(d["durationRange"]["min"]),
                int(d["durationRange"]["max"]),
            )
        except KeyError:
            duration_range = None

        return cls(
            [DeliveryTimeframesDay.from_item(item) for item in d["times"].items()],
            d["isOpenForOrder"],
            d["isOpenForPreorder"],
            d["isScooberRestaurant"],
            duration_range,
        )


@dataclass
class Pickup:
    times: list[DeliveryTimeframesDay]  # probably
    is_open_for_order: bool
    is_open_for_preorder: bool

    @classmethod
    def from_dict(cls, d: dict) -> Self:
        return cls(
            [DeliveryTimeframesDay.from_item(d) for d in d["times"].items()],
            d["isOpenForOrder"],
            d["isOpenForPreorder"],
        )


@dataclass
class ImageRatio:
    category: float
    item: float

    @classmethod
    def from_dict(cls, d: dict) -> Self:
        return cls(
            d["category"],
            d["item"],
        )


@dataclass
class Restaurant:
    delivery_timeframes: list[DeliveryTimeframesDay]
    _list_item: RestaurantListItem
    brand: Brand
    customer_service_food_info_url: str
    rating: Rating
    location: Location
    restaurant_id: str
    colophon: Colophon
    summary: Summary
    delivery: Delivery
    exceptional_status: None  # no idea
    menu: Menu
    pickup: Pickup
    supports: list[SupportOption]
    primary_slug: str
    minisite_url: str | None
    restaurant_hygiene_rating_id: str
    restaurant_phone_number: str
    indicators: list[Indicator]
    payment: Payment
    image_ratio: ImageRatio

    def __getattr__(self, item: str):
        return getattr(self._list_item, item)

    @classmethod
    def from_dict(cls, d: dict, list_item: RestaurantListItem) -> Self:
        times = d.get("delivery", {})["times"]
        delivery_timeframes = [
            DeliveryTimeframesDay.from_item(item) for item in times.items()
        ]
        return cls(
            delivery_timeframes,
            list_item,
            Brand.from_dict_item(list_item.brand, d["brand"]),
            d["customerServiceFoodInfoUrl"],
            Rating.from_dict(d["rating"]),
            Location.from_dict(d["location"]),
            d["restaurantId"],
            Colophon.from_dict(d["colophon"]),
            Summary.from_dict(d["summary"]),
            Delivery.from_dict(d["delivery"]),
            d["exceptionalStatus"],
            Menu.from_dict(d["menu"]),
            Pickup.from_dict(d["pickup"]),
            [SupportOption.from_key(s) for s in d["supports"]],
            d["primarySlug"],
            d["minisiteUrl"],
            d["restaurantHygieneRatingId"],
            d["restaurantPhoneNumber"],
            [Indicator.from_key(i) for i in d["indicators"]],
            Payment.from_dict(d["payment"]),
            ImageRatio.from_dict(d["imageRatio"]),
        )

    @classmethod
    async def from_list_item(
        cls, list_item: RestaurantListItem, *, timeout: int = 15
    ) -> Self:
        url = f"https://cw-api.takeaway.com/api/v33/restaurant?slug={list_item.primary_slug}"
        return await cls.from_url(url, list_item, timeout=timeout)

    @classmethod
    async def from_url(
        cls, url: str, list_item: RestaurantListItem, *, timeout: int = 15
    ) -> Self:
        logger = create_logger(inspect.currentframe().f_code.co_name)  # type: ignore
        logger.debug(f"retrieve {list_item.brand.name}")
        headers = {
            "Accept": "application/json",
            "X-Language-Code": "de",
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0",
            "X-Country-Code": "de",
        }
        async with httpx.AsyncClient() as client:
            response = await client.get(url=url, headers=headers, timeout=timeout)
            response.raise_for_status()
            value = response.json()

        return cls.from_dict(value, list_item)

    def is_open(self) -> bool:
        now = datetime.now().astimezone(tz=ZoneInfo("Europe/Berlin"))
        return any(frame.is_open(now) for frame in self.delivery_timeframes)

    def telegram_markdown_v2(self) -> str:
        brand = escape_markdown(
            self.brand.name
            + (f" ({self.brand.branch_name})" if self.brand.branch_name else "")
        )
        cuisines = escape_markdown(
            ", ".join(
                [cuisine.name() for cuisine in self.cuisine_types if cuisine.name()]
            )
        )
        payment_methods = escape_markdown(", ".join(map(str, self.payment_methods)))
        delivery_info: ShippingInfo = self.delivery_info()
        category_names = "\n".join(
            f"    _{escape_markdown(category.name)}_"
            for category in self.menu.categories
            if "getränke" not in category.name.lower()
        )
        categories = f"Kategorie:\n{category_names}" if category_names else ""
        product_names = "\n".join(
            f"    _{escape_markdown(product.name)}_"
            for product in self.menu.popular_products
        )
        popular_products = (
            f"Populäre Produkte:\n{product_names}" if product_names else ""
        )

        return rf"""*{brand}*
Cuisines: {cuisines if cuisines else "/"}
Lieferzeit: {delivery_info.telegram_markdown_v2()}
{escape_markdown(str(self.rating.score))}⭐ \({self.rating.votes} votes\)
Bezahloptionen: {payment_methods}
{self.location.telegram_markdown_v2()}

{categories}

{popular_products}
"""
