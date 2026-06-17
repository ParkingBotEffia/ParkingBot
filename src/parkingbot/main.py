"""Entry point for ParkingBot."""

import logging
import os

from dotenv import load_dotenv


def configure_logging() -> None:
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def main() -> None:
    load_dotenv()
    configure_logging()
    log = logging.getLogger("parkingbot")
    log.info("ParkingBot starting up...")
    # TODO: build the bot here.


if __name__ == "__main__":
    main()
