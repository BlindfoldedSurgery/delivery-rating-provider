import inspect
import re
from datetime import datetime
from typing import Callable

import httpx
import telegram.constants
from telegram import Update
from telegram.ext import ContextTypes

from provider.context_args import parse_context_args
from provider.filter import (
    default_filter,
    default_filter_args,
    filter_keyword_only_arguments_for_function,
)
from provider.helper import escape_markdown
from provider.logger import create_logger
from provider.takeaway import get_random_restaurants, get_restaurant_list_url
from provider.takeaway.models import Restaurant


async def command_cuisines(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kwargs = default_filter_args()
    kwargs.update(parse_context_args(context.args))
    kwargs.update({"count": 10000})
    url = get_restaurant_list_url(postal_code=kwargs["postal_code"][0])  # type: ignore

    filter_arguments = filter_keyword_only_arguments_for_function(kwargs)
    restaurants = await get_random_restaurants(
        url,
        # caused by PEP 695 generics are not yet supported
        filter_fn=lambda r: default_filter(r, **filter_arguments),  # type: ignore
        count=kwargs["count"],  # type: ignore
        language_code=kwargs["language_code"],
        country_code=kwargs["country_code"],
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
    url = get_restaurant_list_url(postal_code=kwargs["postal_code"][0])  # type: ignore

    filter_arguments = filter_keyword_only_arguments_for_function(kwargs)
    restaurants = await get_random_restaurants(
        url,
        # caused by PEP 695 generics are not yet supported
        filter_fn=lambda r: filter_fn(r, **filter_arguments),  # type: ignore
        count=kwargs["count"],  # type: ignore
        language_code=kwargs["language_code"],
        country_code=kwargs["country_code"],
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
