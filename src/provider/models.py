import inspect
import re
from dataclasses import dataclass
from datetime import datetime
from enum import auto, Enum
from typing import Tuple, Self

import httpx

from provider.logger import create_logger


def escape_markdown(text: str) -> str:
    reserved_characters = [
        "_",
        "*",
        "[",
        "]",
        "(",
        ")",
        "~",
        "`",
        ">",
        "#",
        "+",
        "-",
        "=",
        "|",
        "{",
        "}",
        ".",
        "!",
    ]
    for reserved in reserved_characters:
        text = text.replace(reserved, fr"\{reserved}")

    return text


def to_pascal_case(s: str) -> str:
    if not s:
        return s

    c0 = s[0]
    return "".join([c0.upper(), s[1:]])


class IdEnum(Enum):
    @staticmethod
    def _generate_next_value_(name: str, start: int, count: int, last_values: list) -> str:
        return name

    @classmethod
    def from_key(cls, s: str) -> Self:
        return cls(to_pascal_case(s))


class Indicator(IdEnum):
    IsDeliveryByScoober = auto()
    IsNew = auto()
    IsTestRestaurant = auto()
    IsGroceryStore = auto()
    IsSponsored = auto()
    IsActive = auto()


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
class Rating:
    votes: int
    score: float

    @classmethod
    def from_dict(cls, d: dict[str, int | float]) -> Self:
        return cls(int(d["votes"]), float(d["score"]))


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
        return fr"""{escape_markdown(self._street_address())} \({escape_markdown(self.city)}\)
[Google Maps]({(escape_markdown(self.link()))})"""


class HeroImageUrlType(IdEnum):
    STOCK = auto()
    CHAIN = auto()
    PROFESSIONAL = auto()
    UNKNOWN = auto()
    OWN = auto()
    RANDOM = auto()


@dataclass
class BrandItem:
    name: str
    logo_url: str
    hero_image_url: str
    hero_image_url_type: HeroImageUrlType
    branch_name: str

    @classmethod
    def from_dict(cls, d: dict) -> Self:
        hero_image_url_type = HeroImageUrlType.from_key(d["heroImageUrlType"])

        return cls(
            d["name"],
            d["logoUrl"],
            d["heroImageUrl"],
            hero_image_url_type,
            d["branchName"],
        )

    def hero_image_url_with_parameter(self, parameter: str) -> str:
        """
        examples:
            c_thumb,h_136,w_288/f_auto/q_auto
            ar_50:9,c_thumb,w_940/f_auto/q_auto
            ar_50:9,w_940/f_auto/q_auto

        pass an empty string to get the unmodified version of the hero image

        the c_thumb seems to shift the aspect ratio a bit to a lower height/wider width

        :param parameter: part of url path  which contains the sizes/ratios for the image (see examples)
        :return: formatted hero image url with given parameter
        """
        return self.hero_image_url.format(parameters=parameter)


@dataclass
class Brand:
    chain_id: str
    description: list[str]
    slogan: str
    logo_url: str
    header_image_url: str
    _item: BrandItem

    def __getattr__(self, item):
        return getattr(self._item, item)

    @classmethod
    def from_dict_item(cls, item: BrandItem, d: dict) -> Self:
        return cls(
            d["chainId"],
            d["description"],
            d["slogan"],
            d["logoUrl"],
            d["headerImageUrl"],
            item,
        )


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
            duration_range = (int(d["durationRange"]["min"]), int(d["durationRange"]["max"]))
        except KeyError:
            duration_range = None
        duration = int(d["duration"]) if "duration" in d else None
        delivery_fee_default = float(d["deliveryFeeDefault"]) / 100 if "deliveryFeeDefault" in d else None
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


class PaymentMethod(IdEnum):
    Cash = auto()
    Sofort = auto()
    Paypal = auto()
    Creditcard = auto()
    CreditcardAtHome = auto()
    Giropay = auto()
    Bitpay = auto()
    PinAtHome = auto()

    def __str__(self):
        return str(self.value)


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
            payment_methods
        )

    def offers_delivery(self) -> bool:
        return any(info.is_delivery_info() for info in self.shipping_infos)

    def delivery_info(self) -> ShippingInfo | None:
        if self.offers_delivery():
            return [info for info in self.shipping_infos if info.is_delivery_info()][0]

        return None

    def __hash__(self):
        return hash(self.id)


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

    def __contains__(self, item: datetime) -> bool:
        offset = item.hour * 60 + item.minute

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

    def __contains__(self, item: datetime) -> bool:
        if not self.weekday.is_isoweekday(datetime.now().isoweekday()):
            return False

        return any(item in frame for frame in self.timeframes)


@dataclass
class ChamberOfCommerce:
    issuer: str
    number: str

    @classmethod
    def from_dict(cls, d: dict) -> Self:
        return cls(
            d["issuer"],
            d["number"],
        )


@dataclass
class ColophonData:
    branch_name: str
    restaurant_name: str
    street_name: str
    street_number: str
    postal_code: str
    city: str
    legal_entity: str
    legal_representative_name: str
    legal_name: str
    legal_entity_class: str | None
    email: str
    fax: str
    chamber_of_commerce: list[ChamberOfCommerce]
    vat_number: str
    dispute_resolution_link: str

    @classmethod
    def from_dict(cls, d: dict) -> Self:
        return cls(
            d["branchName"],
            d["restaurantName"],
            d["streetName"],
            d["streetNumber"],
            d["postalCode"],
            d["city"],
            d["legalEntity"],
            d["legalRepresentativeName"],
            d["legalName"],
            d["legalEntityClass"],
            d["email"],
            d["fax"],
            [ChamberOfCommerce.from_dict(coc) for coc in d["chamberOfCommerce"]],
            d["vatNumber"],
            d["disputeResolutionLink"],
        )


@dataclass
class Colophon:
    status: str
    data: ColophonData

    @classmethod
    def from_dict(cls, d: dict) -> Self:
        return cls(
            d["status"],
            ColophonData.from_dict(d["data"]),
        )


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
            duration_range = (int(d["durationRange"]["min"]), int(d["durationRange"]["max"]))
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
        return cls(
            d["unit"],
            int(d["quantity"]) if d["quantity"] else None
        )


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
            d["isExcludedFromMov"]
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


class ShippingType(IdEnum):
    DELIVERY = auto()
    PICKUP = auto()


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
            d["isExcludedFromMov"]
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
            [Variant.from_dict(v, option_groups) for v in d["variants"]]
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
        return cls(
            int(d["demoninator"]),
            CurrencyCode.from_key(d["currencyCode"])
        )


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
class PaymentFee:
    name: str
    type: str
    value: int
    min_value: int
    max_value: int
    shipping_type: ShippingType

    @classmethod
    def from_dict(cls, d: dict) -> Self:
        return cls(
            d["name"],
            d["type"],
            d["value"],
            d["minValue"],
            d["maxValue"],
            ShippingType.from_key(d["shippingType"])
        )


@dataclass
class Message:
    name: str
    messages: list[str]

    @classmethod
    def from_item(cls, item: Tuple[str, list[str]]) -> Self:
        return cls(
            *item
        )


@dataclass
class Issuer:
    pass

    @classmethod
    def from_dict(cls, d: dict) -> Self:
        return cls()


@dataclass
class Payment:
    methods: list[PaymentMethod]
    payment_method_fees: dict  # TODO
    fees: list[PaymentFee]
    messages: list[Message]
    issuers: list[Issuer]  # probably

    @classmethod
    def from_dict(cls, d: dict) -> Self:
        return cls(
            [PaymentMethod.from_key(p) for p in d["methods"]],
            d["paymentMethodFees"],
            [PaymentFee.from_dict(p) for p in d["paymentMethodFees"]],
            [Message.from_item(m) for m in d["messages"].items()],
            [Issuer.from_dict(i) for i in d["issuers"]],
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
        delivery_timeframes = [DeliveryTimeframesDay.from_item(item) for item in times.items()]
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
            ImageRatio.from_dict(d["imageRatio"])
        )

    @classmethod
    async def from_list_item(cls, list_item: RestaurantListItem, *, timeout: int = 15) -> Self:
        url = f"https://cw-api.takeaway.com/api/v33/restaurant?slug={list_item.primary_slug}"
        return await cls.from_url(url, list_item, timeout=timeout)

    @classmethod
    async def from_url(cls, url: str, list_item: RestaurantListItem, *, timeout: int = 15) -> Self:
        logger = create_logger(inspect.currentframe().f_code.co_name)  # type: ignore
        logger.debug(f"retrieve {list_item.brand.name}")
        headers = {
            'Accept': 'application/json',
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
        now = datetime.now()
        return any(now in frame for frame in self.delivery_timeframes)

    def telegram_markdown_v2(self) -> str:
        brand = escape_markdown(self.brand.name + (f" ({self.brand.branch_name})" if self.brand.branch_name else ""))
        cuisines = escape_markdown(", ".join([cuisine.name() for cuisine in self.cuisine_types if cuisine.name()]))
        payment_methods = escape_markdown(", ".join(map(str, self.payment_methods)))
        delivery_info: ShippingInfo = self.delivery_info()
        category_names = "\n".join(f"    _{escape_markdown(category.name)}_" for category in self.menu.categories if
                                       "getränke" not in category.name.lower())
        categories = f"Kategorie:\n{category_names}" if category_names else ""
        product_names = "\n".join(f"    _{escape_markdown(product.name)}_" for product in self.menu.popular_products)
        popular_products = f"Populäre Produkte:\n{product_names}" if product_names else ''

        return fr"""*{brand}*
Cuisines: {cuisines if cuisines else "/"}
Lieferzeit: {delivery_info.telegram_markdown_v2()}
{escape_markdown(str(self.rating.score))}⭐ \({self.rating.votes} votes\)
Bezahloptionen: {payment_methods}
{self.location.telegram_markdown_v2()}

{categories}

{popular_products}
"""
