import inspect
import os
import re
from datetime import datetime
from typing import Callable, Any

import httpx
import telegram.constants
from telegram import Update
from telegram.ext import ContextTypes

from provider.helper import escape_markdown
from provider.logger import create_logger
from provider.takeaway import get_random_restaurants, get_restaurant_list_url
from provider.takeaway.models import Restaurant, SupportOption
from provider.takeaway.models.restaurant_list_item import CuisineType

DEFAULT_POSTAL_CODE = int(os.getenv("DEFAULT_POSTAL_CODE", 64293))


def default_filter_args() -> dict[str, Any]:
    return {"postal_code": DEFAULT_POSTAL_CODE, "cities_to_ignore": [], "count": 1}


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
    :param cities_to_ignore: list of cities to ignore (default is 'frankfurt' for the postal code 64293)
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


def get_filter_arguments(kwargs: dict) -> dict:
    _default_filter_kwargs = inspect.getfullargspec(default_filter).kwonlyargs
    return {k: v for k, v in kwargs.items() if k in _default_filter_kwargs}


def parse_context_args(_args: list[str] | None) -> dict:
    if not _args:
        return {}

    args = "\n".join(_args)

    kwargs: dict[str, Any] = default_filter_args()

    # int/float
    kwargs.update({k.lower(): float(v) for k, v in re.findall(r"(\w+):(\d+(?:\.\d+)?)", args)})

    # bool
    kwargs.update(
        {
            k.lower(): v.lower() in ["yes", "true"]
            for k, v in re.findall(r"(\w+):(no|yes|true|false)", args)
            if k not in kwargs.keys()
        }
    )

    # list[str]
    kwargs.update(
        {
            k.lower(): v.split(",")
            for k, v in re.findall(r"(\w+):((?:[\w-]+,?)+)", args)
            if k not in kwargs.keys()
        }
    )

    # validate keyword types (for bool/float/int)
    argspec = inspect.getfullargspec(default_filter)
    kwonly_annotations = {k: v for k, v in argspec.annotations.items() if k in argspec.kwonlyargs}
    for keyword, keyword_type in kwonly_annotations.items():
        if value := kwargs.get(keyword):
            if value is None:
                continue
            elif keyword_type == bool:
                if not isinstance(value, bool):
                    raise ValueError(f"invalid boolean value for {keyword}")
            elif keyword_type == int or keyword_type == float:
                if not (isinstance(value, int) or isinstance(value, float)):
                    raise ValueError(f"invalid int/float input for {keyword}")

    if kwargs["postal_code"] == DEFAULT_POSTAL_CODE:
        kwargs["cities_to_ignore"] += ["frankfurt"]  # type: ignore

    return kwargs


async def command_cuisines(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kwargs = default_filter_args()
    kwargs.update(parse_context_args(context.args))
    kwargs.update({"count": 10000})
    url = get_restaurant_list_url(postal_code=kwargs["postal_code"])  # type: ignore

    filter_arguments = get_filter_arguments(kwargs)
    restaurants = await get_random_restaurants(
        url,
        # caused by PEP 695 generics are not yet supported
        filter_fn=lambda r: default_filter(r, **filter_arguments),  # type: ignore
        count=kwargs["count"],  # type: ignore
    )

    cuisine_types = set()
    for restaurant in restaurants:
        cuisine_types.update(restaurant.cuisine_types)

    cuisine_names = [ct.name() for ct in cuisine_types if ct]
    message = sorted([name for name in cuisine_names if name])
    return await update.effective_message.reply_text(text="\n".join(message))  # type: ignore


def parse_parameter_description_from_docstring(docstring: str | None) -> dict[str, str]:
    if docstring is None:
        return {}

    return {match[0]: match[1] for match in re.findall(r":param (\w+): (.+)", docstring)}


def get_default_values_for_function(function: Callable) -> dict[str, str]:
    argspec = inspect.getfullargspec(function)
    kwonlydefaults = argspec.kwonlydefaults
    if kwonlydefaults is None:
        return {}

    defaults = {}

    for key, default in kwonlydefaults.items():
        if default is None:
            defaults[key] = "`empty`"
        else:
            defaults[key] = f"`{default}`".lower()

    return defaults


async def command_get_available_filter_arguments(update: Update, _: ContextTypes.DEFAULT_TYPE):
    param_description = parse_parameter_description_from_docstring(default_filter.__doc__)
    defaults = get_default_values_for_function(default_filter)
    argspec = inspect.getfullargspec(default_filter)
    kwonly_annotations = {k: v for k, v in argspec.annotations.items() if k in argspec.kwonlyargs}
    message = [
        "filter args can be given as followed: `{key}:{value}`\n"
        r"e\.g\.: `minimum_rating_score:3\.0`",
        "allowed values for booleans: no, false, yes, true",
        r"lists \(default: empty\) can be a comma seperated list \(e\.g\. a,b,c\)"
        r"allowed characters are: a\-z, A\-Z, \-, \_",
    ]
    for keyword, keyword_type in kwonly_annotations.items():
        message.append(
            f"`{escape_markdown(keyword)}`: "
            + escape_markdown(param_description[keyword])
            + rf" \| default: {defaults[keyword]}"
        )

    return await update.effective_message.reply_text(  # type: ignore
        text="\n\n".join(message), parse_mode=telegram.constants.ParseMode.MARKDOWN_V2
    )


async def command_random[
    #   PEP 695 generics are not yet supported
    **P  # type: ignore
](
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    # caused by  PEP 695 generics are not yet supported
    filter_fn: Callable[  # type: ignore
        [
            Restaurant,
            P.kwargs,
        ],
        bool,
        # caused by  PEP 695 generics are not yet supported
    ] = default_filter,  # type: ignore
):
    logger = create_logger(inspect.currentframe().f_code.co_name)  # type: ignore
    kwargs = default_filter_args()

    if context.args:
        kwargs.update(parse_context_args(context.args))

    start = datetime.now()
    url = get_restaurant_list_url(postal_code=kwargs["postal_code"])  # type: ignore

    filter_arguments = get_filter_arguments(kwargs)
    restaurants = await get_random_restaurants(
        url,
        # caused by PEP 695 generics are not yet supported
        filter_fn=lambda r: filter_fn(r, **filter_arguments),  # type: ignore
        count=kwargs["count"],  # type: ignore
    )
    if restaurants:
        logger.debug(f"{(datetime.now() - start).seconds}s to retrieve filtered restaurant list")
        message = f"\n{escape_markdown('=================================')}\n\n".join(
            [restaurant.telegram_markdown_v2() for restaurant in restaurants]
        )
    else:
        message = "couldn't find any restaurant for the given filter"

    # mypy complains that `effective_message` might be None, this cannot happen here since
    # we're only calling this method from the `CommandHandler` which forces
    # `effective_message` to be not `None`
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
    except ValueError as e:
        message = str(e)

    message = escape_markdown(message)

    # mypy complains that `effective_message` might be None, this cannot happen here since
    # this method only called by the error handler which forces `effective_message` to be not `None`
    # due to us having only `CommandHandler`s registered
    return await update.effective_message.reply_text(  # type: ignore
        message,
        reply_to_message_id=update.effective_message.message_id,  # type: ignore
        disable_web_page_preview=True,
    )
