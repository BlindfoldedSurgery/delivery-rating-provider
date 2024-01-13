import asyncio
import inspect
import random
from typing import Optional, Callable

import httpx
from aiocache import cached

from provider.logger import create_logger
from provider.takeaway.models import RestaurantListItem, Restaurant


def get_restaurant_list_url(
    postal_code: int,
    *,
    base_url: str = "https://cw-api.takeaway.com",
    limit: int = 0,
    is_accurate: bool = True,
    show_test_restaurants: bool = False,
) -> str:
    is_accurate_url: str = str(is_accurate).lower()
    show_test_restaurants_url: str = str(show_test_restaurants).lower()

    return (
        f"{base_url}/api/v33/restaurants?postalCode={postal_code}&limit={limit}"
        f"&isAccurate={is_accurate_url}&filterShowTestRestaurants={show_test_restaurants_url}"
    )


@cached(ttl=1800)
async def retrieve_restaurants(_url: str, *, timeout: int) -> list[RestaurantListItem]:
    logger = create_logger(inspect.currentframe().f_code.co_name)  # type: ignore
    logger.debug(f"retrieve restaurant list for {_url}")
    headers = {
        "Accept": "application/json",
        "X-Language-Code": "de",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0",
        "X-Country-Code": "de",
    }

    response = httpx.get(_url, headers=headers, timeout=timeout)
    response.raise_for_status()
    restaurants = response.json().get("restaurants", [])

    return [
        RestaurantListItem.from_dict(restaurants[restaurant_key])
        for restaurant_key in restaurants
    ]


async def get_random_restaurants(
    url: str,
    *,
    count: int = 1,
    filter_fn: Optional[Callable[[Restaurant], bool]] = None,
    timeout: int = 15,
) -> list[Restaurant]:
    """
    :raises IndexError: if no restaurants have been
    :param url: URL to list all restaurants
    :param count: number of restauants to return
    :param filter_fn: filter restaurants (e.g. Restaurant#is_open)
    :param timeout: timeout for each restaurant page and the listing page
    :return: restaurant from the given list which matches the filters
    """
    log = create_logger(inspect.currentframe().f_code.co_name)  # type: ignore
    list_items: list[RestaurantListItem] = await retrieve_restaurants(
        url, timeout=timeout
    )

    # make mypy happy
    chosen_restaurants: list[Restaurant]
    if filter_fn is not None:
        restaurants_a = (
            Restaurant.from_list_item(list_item, timeout=timeout)
            for list_item in list_items
        )
        restaurants = await asyncio.gather(*restaurants_a, return_exceptions=True)

        filtered_restaurants = [
            _restaurant
            for _restaurant in restaurants
            if not isinstance(_restaurant, BaseException) and filter_fn(_restaurant)
        ]

        for error in [
            restaurant
            for restaurant in restaurants
            if isinstance(restaurant, BaseException)
        ]:
            log.exception(repr(error))

        chosen_restaurants = list(filtered_restaurants)
    else:
        chosen_restaurants = [
            await Restaurant.from_list_item(list_item) for list_item in list_items
        ]

    count = min(count, len(chosen_restaurants))
    return random.choices(chosen_restaurants, k=count)
