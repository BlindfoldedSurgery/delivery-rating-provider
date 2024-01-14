import inspect
from typing import Callable, Any

from provider.config import DEFAULT_POSTAL_CODE
from provider.takeaway.models import SupportOption, Restaurant
from provider.takeaway.models.restaurant_list_item import CuisineType


def default_filter_args() -> dict[str, Any]:
    return {
        "postal_code": DEFAULT_POSTAL_CODE,
        "cities_to_ignore": [],
        "count": 1,
        "language_code": "de",
        "country_code": "de",
    }


def filter_cuisines(
    restaurant: Restaurant, cuisines: list[str] | None, *, exclude: bool = False
) -> bool:
    if cuisines is None:
        return not exclude

    if not exclude:
        if len(cuisines) == 0:
            return True

    cuisine_types = [CuisineType.from_str(c) for c in cuisines]
    return any([True for cuisine_type in cuisine_types if cuisine_type in restaurant.cuisine_types])


def filter_city(restaurant: Restaurant, cities_to_ignore: list[str] | None) -> bool:
    if cities_to_ignore is None:
        return True

    return any(
        [
            True
            for to_ignore in cities_to_ignore
            if to_ignore.lower() in restaurant.location.city.lower()
        ]
    )


def default_filter(
    restaurant: Restaurant,
    *,
    max_order_value: float = 50.0,
    max_duration: int = 90,
    minimum_rating_score: float = 2.1,
    minimum_rating_votes: int = 1,
    cities_to_ignore: list[str] | None = None,
    is_open_in_minutes: int = 0,
    cuisines_to_include: list[str] | None = None,
    cuisines_to_exclude: list[str] | None = None,
    allow_pickup: bool = False,
) -> bool:
    """

    :param restaurant:
    :param max_order_value: minimum order value must be below (or equal to) this threshold
    :param max_duration: maximum delivery duration in minutes
    :param minimum_rating_score: minimum rating score (0.0 - 5.0)
    :param minimum_rating_votes: minimum votes for the restaurant
    :param cities_to_ignore: list of cities to ignore (default is 'frankfurt' for the postal code '64293')
    :param is_open_in_minutes: include restaurants which open x minutes from now
    :param cuisines_to_include: list of cuisines which a restaurant must include
    :param cuisines_to_exclude: list of cuisines which must not appear in restaurants choices
    :param allow_pickup: by default only restaurants which support delivery are filtered
    :return: whether the restaurant fulfills all the given criteria
    """
    delivery_info = restaurant.delivery_info()
    min_order_value = delivery_info.min_order_value if delivery_info else None
    duration = delivery_info.duration if delivery_info else None

    is_city_to_ignore = filter_city(restaurant, cities_to_ignore)

    has_cuisine_to_exclude = filter_cuisines(restaurant, cuisines_to_exclude, exclude=True)
    has_cuisine_to_include = filter_cuisines(restaurant, cuisines_to_include, exclude=False)

    pickup_delivery = (
        allow_pickup and restaurant.supports(SupportOption.Pickup)
    ) or delivery_info is not None

    return all(
        [
            restaurant.is_open(is_open_in_minutes),
            restaurant.offers_delivery(),
            restaurant.rating.votes >= minimum_rating_votes,
            restaurant.rating.score >= minimum_rating_score,
            min_order_value is None or min_order_value <= max_order_value,
            duration is None or duration <= max_duration,
            not is_city_to_ignore,
            has_cuisine_to_include,
            not has_cuisine_to_exclude,
            pickup_delivery,
        ]
    )


def filter_keyword_only_arguments_for_function(
    kwargs: dict, *, function: Callable = default_filter
) -> dict:
    _default_filter_kwargs = inspect.getfullargspec(function).kwonlyargs
    return {k: v for k, v in kwargs.items() if k in _default_filter_kwargs}
