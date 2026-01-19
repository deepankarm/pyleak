from __future__ import annotations

import logging
import os
import traceback
from dataclasses import dataclass


def setup_logger(name: str = __name__):
    logger = logging.getLogger(name)
    logger.setLevel(os.getenv("PYLEAK_LOG_LEVEL", "WARNING").upper())
    logger.addHandler(logging.StreamHandler())
    return logger


@dataclass
class CallerContext:
    filename: str
    name: str
    lineno: int | None = None
    files: set[str] | None = None

    def __str__(self):
        return f"{self.filename}:{self.name}:{self.lineno or '?'}"


def find_my_caller(ignore_frames: int = 2) -> CallerContext | None:
    """detect using the stack trace"""

    stack = traceback.extract_stack()

    # ignore 2 frames
    # 1. the first frame which is `find_my_caller` itself
    # 2. the second frame if the function that called `find_my_caller`
    frame = stack[-ignore_frames - 1]
    files = {f.filename for f in stack[:-ignore_frames]}
    return CallerContext(
        filename=frame.filename, name=frame.name, lineno=frame.lineno, files=files
    )
