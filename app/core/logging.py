import logging
from contextlib import contextmanager

from .config import get_settings


@contextmanager
def configure_logging():
    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logging.basicConfig(level=level, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    try:
        yield
    finally:
        logging.shutdown()
