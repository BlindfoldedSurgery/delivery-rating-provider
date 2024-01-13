from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum, auto
from typing import Self, Tuple

import math

from provider.helper import escape_markdown, to_pascal_case


class IdEnum(Enum):
    @staticmethod
    def _generate_next_value_(name: str, start: int, count: int, last_values: list) -> str:
        return name

    @classmethod
    def from_key(cls, s: str) -> Self:
        return cls(to_pascal_case(s))

    def __eq__(self, other):
        return self.value == other.value


class ShippingType(IdEnum):
    DELIVERY = auto()
    PICKUP = auto()


class Weekday(Enum):
    @staticmethod
    def _generate_next_value_(name: str, start: int, count: int, last_values: list) -> int:
        return len(last_values)

    Sunday = auto()
    Monday = auto()
    Tuesday = auto()
    Wednesday = auto()
    Thursday = auto()
    Friday = auto()
    Saturday = auto()

    def is_isoweekday(self, iso_weekday: int) -> bool:
        if self == Weekday.Sunday:
            return iso_weekday == 7

        return self.value == iso_weekday


@dataclass
class DeliveryTimeframe:
    start: int
    end: int
    formatted_start: str
    formatted_end: str

    @classmethod
    def from_dict(cls, d: dict) -> Self:
        return cls(
            int(d["start"]),
            int(d["end"]),
            d["formattedStart"],
            d["formattedEnd"],
        )

    def is_open(self, item: datetime, is_open_in_minutes: int) -> bool:
        offset_day = 0
        hours_diff = self.end // 60

        if hours_diff > 24:
            # we're gonna ignore seconds here (not even supported by takeaway)
            rem = int(abs(math.remainder(self.end, 60)))
            item = item.replace(day=item.day - 1, hour=(hours_diff - 24), minute=rem) + timedelta(
                minutes=is_open_in_minutes
            )
            offset_day = 24

        offset = ((offset_day + item.hour) * 60) + item.minute

        return self.start <= offset <= self.end


@dataclass
class DeliveryTimeframesDay:
    timeframes: list[DeliveryTimeframe]
    weekday: Weekday

    @classmethod
    def from_item(cls, item: Tuple[int, list[dict]]) -> Self:
        return cls(
            [DeliveryTimeframe.from_dict(d) for d in item[1]],
            Weekday(int(item[0])),
        )

    def is_open(self, item: datetime, is_open_in_minutes: int) -> bool:
        return any(frame.is_open(item, is_open_in_minutes) for frame in self.timeframes)


class PaymentMethod(IdEnum):
    Cash = auto()
    Sofort = auto()
    Paypal = auto()
    Creditcard = auto()
    CreditcardAtHome = auto()
    Giropay = auto()
    Bitpay = auto()
    PinAtHome = auto()
    Twint = auto()
    Postfinance = auto()

    def __str__(self):
        return str(self.value)


class Indicator(IdEnum):
    IsDeliveryByScoober = auto()
    IsNew = auto()
    IsTestRestaurant = auto()
    IsGroceryStore = auto()
    IsSponsored = auto()
    IsActive = auto()


@dataclass
class Rating:
    votes: int
    score: float

    @classmethod
    def from_dict(cls, d: dict[str, int | float]) -> Self:
        return cls(int(d["votes"]), float(d["score"]))


@dataclass
class Location:
    # either `streetAddress` or (`streetName`, `streetNumber`) are defined
    street_address: str | None
    street_name: str | None
    street_number: str | None
    city: str
    country: str
    lat: float
    lon: float
    timezone: str

    @classmethod
    def from_dict(cls, d: dict) -> Self:
        return cls(
            d.get("streetAddress"),
            d.get("streetName"),
            d.get("streetNumber"),
            d["city"],
            d["country"],
            float(d["lat"]),
            float(d["lng"]),
            d["timeZone"],
        )

    def link(self) -> str:
        # see https://developers.google.com/maps/documentation/urls/get-started#search-examples
        return f"https://www.google.com/maps/search/?api=1&query={self.lat}%2C{self.lon}"

    def _street_address(self) -> str:
        if self.street_address:
            return self.street_address

        return f"{self.street_name} {self.street_number}"

    def telegram_markdown_v2(self) -> str:
        return rf"""{escape_markdown(self._street_address())} \({escape_markdown(self.city)}\)
[Google Maps]({(escape_markdown(self.link()))})"""


class SupportOption(IdEnum):
    Delivery = auto()
    Pickup = auto()
    Vouchers = auto()
    StampCards = auto()
    Discounts = auto()
    ProductRemarks = auto()
    OnlinePayments = auto()
    Tipping = auto()


@dataclass
class LowestDeliveryFee:
    _from: int
    to: int | None
    fee: int

    @classmethod
    def from_dict(cls, d: dict) -> Self:
        to = int(d["to"]) if "to" in d else None
        return cls(int(d["from"]), to, int(d["fee"]))


@dataclass
class ShippingInfo:
    type: str
    is_open_for_order: bool
    is_open_for_preorder: bool
    opening_time: str | None
    duration: int | None
    duration_range: Tuple[int, int] | None
    delivery_fee_default: float | None
    min_order_value: float | None
    lowest_delivery_fee: LowestDeliveryFee | None

    # DynamicDeliveryFeeInfo

    def is_delivery_info(self):
        return self.type == "delivery"

    @classmethod
    def from_dict(cls, item: Tuple[str, dict]) -> Self:
        _type = item[0]
        d = item[1]
        try:
            lowest_delivery_fee = LowestDeliveryFee.from_dict(d["lowestDeliveryFee"])
        except KeyError:
            lowest_delivery_fee = None
        try:
            duration_range = (
                int(d["durationRange"]["min"]),
                int(d["durationRange"]["max"]),
            )
        except KeyError:
            duration_range = None
        duration = int(d["duration"]) if "duration" in d else None
        delivery_fee_default = (
            float(d["deliveryFeeDefault"]) / 100 if "deliveryFeeDefault" in d else None
        )
        min_order_value = float(d["minOrderValue"]) / 100 if "minOrderValue" in d else None

        return cls(
            _type,
            d["isOpenForOrder"],
            d["isOpenForPreorder"],
            d["openingTime"],
            duration,
            duration_range,
            delivery_fee_default,
            min_order_value,
            lowest_delivery_fee,
        )

    def format_delivery(self) -> str:
        s = f"{self.duration}min"
        if self.duration_range:
            s += f" ({self.duration_range[0]} - {self.duration_range[1]})\n"
        else:
            s += "\n"
        if self.delivery_fee_default:
            s += f"Lieferkosten: {self.delivery_fee_default}€\n"
        if self.min_order_value:
            s += f"Mindestbestellwert: {self.min_order_value}€\n"

        return s.rstrip("\n")

    def telegram_markdown_v2(self) -> str:
        if self.is_delivery_info():
            return escape_markdown(self.format_delivery())

        return ""
