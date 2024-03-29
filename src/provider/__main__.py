import inspect
import os
import sys

import telegram.ext
from telegram.ext import ApplicationBuilder

from provider import bot
from provider.logger import create_logger


def get_env_or_die(key: str) -> str:
    logger = create_logger(inspect.currentframe().f_code.co_name)  # type: ignore
    if token := os.getenv(key):
        return token

    logger.error(f"failed to retrieve token from environment (`{key}`)")
    sys.exit(1)


def main():
    bot_token = get_env_or_die("BOT_TOKEN")
    application = ApplicationBuilder().token(bot_token).build()

    for handler in [
        telegram.ext.CommandHandler("random", bot.command_random),
        telegram.ext.CommandHandler(
            "get_available_filter_arguments", bot.command_get_available_filter_arguments
        ),
        telegram.ext.CommandHandler("cuisines", bot.command_cuisines),
    ]:
        application.add_handler(handler)

    # noinspection PyTypeChecker
    application.add_error_handler(bot.error_handler)
    create_logger(inspect.currentframe().f_code.co_name).info("Starting")
    application.run_polling()


if __name__ == "__main__":
    main()
