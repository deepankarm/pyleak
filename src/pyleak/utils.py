import logging
import os


def setup_logger(name: str = __name__):
    logger = logging.getLogger(name)
    logger.setLevel(os.getenv("PYLEAK_LOG_LEVEL", "WARNING").upper())
    logger.addHandler(logging.StreamHandler())
    return logger
