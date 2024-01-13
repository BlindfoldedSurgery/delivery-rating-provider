import inspect
import os
import re
from datetime import datetime
from typing import Callable

import httpx
import telegram.constants
from telegram import Update
from telegram.ext import ContextTypes

from provider.helper import escape_markdown
from provider.logger import create_logger
from provider.takeaway import get_random_restaurants, get_restaurant_list_url
from provider.takeaway.models import Restaurant

DEFAULT_POSTAL_CODE = int(os.getenv("DEFAULT_POSTAL_CODE", 64293))


def default_filter(
    restaurant: Restaurant,
    *,
    max_order_value: float = 50.0,
    max_duration: int = 90,
    minimum_rating_score: float = 2.1,
    minimum_rating_votes: int = 1,
    cities_to_ignore: list[str] | None = None,
    is_open_in_minutes: int = 0,
) -> bool:
    if cities_to_ignore is None:
        cities_to_ignore = []

    delivery_info = restaurant.delivery_info()
    min_order_value = delivery_info.min_order_value if delivery_info else None
    duration = delivery_info.duration if delivery_info else None

    is_city_to_ignore = any(
        [
            True
            for to_ignore in cities_to_ignore
            if to_ignore.lower() in restaurant.location.city.lower()
        ]
    )
    return all(
        [
            restaurant.is_open(is_open_in_minutes),
            restaurant.offers_delivery(),
            restaurant.rating.votes >= minimum_rating_votes,
            restaurant.rating.score >= minimum_rating_score,
            min_order_value is None or min_order_value <= max_order_value,
            duration is None or duration <= max_duration,
            not is_city_to_ignore,
        ]
    )


async def command_get_available_filter_arguments(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    argspec = inspect.getfullargspec(default_filter)
    kwonly_annotations = {
        k: v for k, v in argspec.annotations.items() if k in argspec.kwonlyargs
    }
    message = [
        "filter args can be given as followed: `{key}:{value}`\n"
        r"e\.g\.: `minimum_rating_score:3\.0`",
    ]
    for keyword, keyword_type in kwonly_annotations.items():
        if keyword_type == int or keyword_type == float:
            message.append(
                f"`{escape_markdown(keyword)}`"
                + escape_markdown(": a number (e.g. 1, 1.0)")
            )
        elif (
            str(keyword_type) == "list[str]" or str(keyword_type) == "list[str] | None"
        ):
            message.append(
                f"`{escape_markdown(keyword)}`"
                + escape_markdown(
                    ": a comma separated string (only a-z, underscores and dashes allowed, e.g. a-d, b)"
                )
            )
        else:
            message.append(
                f"`{escape_markdown(keyword)}` is of type *{escape_markdown(str(keyword_type))}*"
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
    kwargs = {"postal_code": DEFAULT_POSTAL_CODE, "count": 1, "cities_to_ignore": []}

    if context.args:
        args = "\n".join(context.args)
        kwargs.update(
            {k.lower(): float(v) for k, v in re.findall(r"(\w+):(\d+(?:\.\d+)?)", args)}
        )
        kwargs.update(
            {
                k.lower(): v.split(",")
                for k, v in re.findall(r"(\w+):((?:[\w-]+,?)+)", args)
            }
        )
    if kwargs["postal_code"] == DEFAULT_POSTAL_CODE:
        kwargs["cities_to_ignore"] += ["frankfurt"]  # type: ignore

    start = datetime.now()
    url = get_restaurant_list_url(postal_code=kwargs["postal_code"])  # type: ignore

    default_filter_kwargs = inspect.getfullargspec(default_filter).kwonlyargs
    filter_arguments = {k: v for k, v in kwargs.items() if k in default_filter_kwargs}
    restaurants = await get_random_restaurants(
        url,
        # caused by PEP 695 generics are not yet supported
        filter_fn=lambda r: filter_fn(r, **filter_arguments),  # type: ignore
        count=kwargs["count"],  # type: ignore
    )
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

    # mypy complains that `effective_message` might be None, this cannot happen here since
    # this method only called by the error handler which forces `effective_message` to be not `None`
    # due to us having only `CommandHandler`s registered
    return await update.effective_message.reply_text(  # type: ignore
        message,
        reply_to_message_id=update.effective_message.message_id,  # type: ignore
        disable_web_page_preview=True,
    )
