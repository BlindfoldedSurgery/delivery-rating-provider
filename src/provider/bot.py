import asyncio
import inspect
import random
from datetime import datetime
from typing import Optional, Callable

import httpx
import telegram.constants
from telegram import Update
from telegram.ext import ContextTypes

from provider.logger import create_logger
from provider.models import RestaurantListItem, Restaurant, escape_markdown


def get_restaurant_list_url(
    postal_code: str,
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


def retrieve_restaurants(_url: str, *, timeout: int) -> list[RestaurantListItem]:
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
    list_items: list[RestaurantListItem] = retrieve_restaurants(url, timeout=timeout)

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


def default_filter(restaurant: Restaurant) -> bool:
    delivery_info = restaurant.delivery_info()
    min_order_value = delivery_info.min_order_value if delivery_info else None
    duration = delivery_info.duration if delivery_info else None

    return all(
        [
            restaurant.is_open(),
            restaurant.offers_delivery(),
            restaurant.rating.votes > 0,
            restaurant.rating.score > 2.0,
            min_order_value is None or min_order_value < 50.0,
            "frankfurt" not in restaurant.location.city.lower(),
            duration is None or restaurant.delivery_info().duration < 90,
        ]
    )


async def command_random(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    filter_fn: Callable[[Restaurant], bool] = default_filter,
):
    logger = create_logger(inspect.currentframe().f_code.co_name)  # type: ignore
    postal_code = "64293"
    count = 1

    if context.args:
        postal_code = context.args[0]
        logger.debug(f"retrieving items for postal code {postal_code}")

    start = datetime.now()
    url = get_restaurant_list_url(postal_code=postal_code)
    restaurants = await get_random_restaurants(url, filter_fn=filter_fn, count=count)
    if restaurants:
        logger.debug(
            f"{(datetime.now() - start).seconds}s to retrieve filtered restaurant list"
        )
        message = f"\n{escape_markdown('=================================')}\n\n".join(
            [restaurant.telegram_markdown_v2() for restaurant in restaurants]
        )
    else:
        message = "couldn't find any restaurant for the given filter"

    # mypy complains that `effective_message` might be None, this cannot happen here since
    # we're only calling this method from the `CommandHandler` which forces `effective_message` to be not `None`
    return await update.effective_message.reply_text(  # type: ignore
        message,
        disable_web_page_preview=True,  # type: ignore
        parse_mode=telegram.constants.ParseMode.MARKDOWN_V2,
    )


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log = create_logger(inspect.currentframe().f_code.co_name)  # type: ignore

    try:
        raise context.error  # type: ignore
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            message = "Cannot complete action, failed to authorize to TimApi"
        elif e.response.status_code == 403:
            message = "Cannot complete action, it is forbidden"
        elif e.response.status_code == 409:
            message = "Movie is already enqueued/has been watched"
        else:
            message = f"Unhandled status code error:\n{str(e)}"
    except httpx.HTTPError as e:
        message = "failed to complete action"
        log.error(message, exc_info=True)
        message += f"\n{str(e)}"
    except telegram.error.BadRequest as e:
        message = f"failed to send reply: {str(e)}"

    message = escape_markdown(message)
    return await update.effective_message.reply_text(  # type: ignore
        message,
        reply_to_message_id=update.effective_message.message_id,  # type: ignore
        disable_web_page_preview=True,
    )
