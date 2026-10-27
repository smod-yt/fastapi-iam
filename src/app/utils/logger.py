import sys
from pathlib import Path

from loguru import logger

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
LOG_DIR = BASE_DIR / "logs"


def startup_logger():
    logger.remove()

    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level="DEBUG",
    )

    logger.add(
        LOG_DIR / "app.log",
        rotation="10 MB",
        retention="30 days",
        compression="zip",
        level="INFO",
        encoding="utf-8",
    )

    logger.info("Logger successfully started")
