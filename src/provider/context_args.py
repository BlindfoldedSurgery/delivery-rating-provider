import inspect
import re
from typing import Callable, Any

from provider.config import DEFAULT_POSTAL_CODE
from provider.filter import default_filter, default_filter_args


def parse_context_args_regex(
    argument: str,
    value_map_fn: Callable[[str], Any],
    regex: str,
    key_map_fn: Callable[[str], str] = str.lower,
    filter_fn: Callable[[str], bool] = lambda _: True,
    exclude_keys: list[str] | None = None,
) -> dict:
    if exclude_keys is None:
        exclude_keys = []
    return {
        key_map_fn(k): value_map_fn(v)
        for k, v in re.findall(regex, argument)
        if filter_fn(v) and k not in exclude_keys
    }


def is_truthy_boolean_string(value: str) -> bool:
    return value.lower() in ["yes", "true"]


def validate_keyword_types(kwargs: dict, *, function: Callable = default_filter) -> None:
    """
    :raises: ValueError when any keyword argument does not match the excpected type
    """
    # validate keyword types (for bool/float/int)
    argspec = inspect.getfullargspec(function)
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


def parse_context_args(_args: list[str] | None) -> dict[str, list[str] | bool | int | float]:
    if not _args:
        return {}

    args = "\n".join(_args)

    kwargs: dict[str, Any] = default_filter_args()
    default_keys = list(kwargs.keys())

    # int/float
    kwargs.update(
        parse_context_args_regex(args, value_map_fn=float, regex=r"(\w+):(\d+(?:\.\d+)?)")
    )
    # bool
    kwargs.update(
        parse_context_args_regex(
            args,
            value_map_fn=is_truthy_boolean_string,
            regex=r"(\w+):(no|yes|true|false)",
            exclude_keys=list(set(list(kwargs.keys())) - set(default_keys)),
        )
    )
    # list[str]
    kwargs.update(
        parse_context_args_regex(
            args,
            value_map_fn=lambda v: v.split(","),
            regex=r"(\w+):((?:[\w-]+,?)+)",
            exclude_keys=list(set(list(kwargs.keys())) - set(default_keys)),
        )
    )

    validate_keyword_types(kwargs)

    if kwargs["postal_code"] == DEFAULT_POSTAL_CODE:
        kwargs["cities_to_ignore"] += ["frankfurt"]  # type: ignore

    return kwargs
