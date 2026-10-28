import asyncio
import logging
import sys

from config.settings import Settings, setup_logging
from bot.app import start_application

logger = logging.getLogger("main")


def main() -> None:
    try:
        settings = Settings()
    except Exception as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        print("Please ensure .env file is present or environment variables are set.", file=sys.stderr)
        sys.exit(1)

    setup_logging(settings)
    logger.info("Starting tg-saver bot...")

    try:
        asyncio.run(start_application(settings))
    except (KeyboardInterrupt, SystemExit):
        logger.info("Application stopped by user.")
    except Exception as e:
        logger.exception("Fatal error during bot execution: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
