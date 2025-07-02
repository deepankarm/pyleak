"""
Thread Leak Detector

Detect and handle leaked threads in Python.
"""

import logging
import re
import threading
import time
from typing import List, Optional, Set, Union

from pyleak.base import (
    LeakAction,
    LeakError,
    _BaseLeakContextManager,
    _BaseLeakDetector,
)
from pyleak.utils import setup_logger

_logger = setup_logger(__name__)
DEFAULT_THREAD_NAME_FILTER = re.compile(r"^(?!asyncio_\d+$).*")


class ThreadLeakError(LeakError):
    """Raised when thread leaks are detected and action is set to RAISE."""


class _ThreadLeakDetector(_BaseLeakDetector):
    """Core thread leak detection functionality."""

    def __init__(
        self,
        action: LeakAction = LeakAction.WARN,
        name_filter: Optional[Union[str, re.Pattern]] = DEFAULT_THREAD_NAME_FILTER,
        logger: Optional[logging.Logger] = _logger,
        exclude_daemon: bool = True,
    ):
        super().__init__(action, name_filter, logger)
        self.exclude_daemon = exclude_daemon

    def _get_resource_name(self, thread: threading.Thread) -> str:
        """Get thread name, handling both named and unnamed threads."""
        name = thread.name
        return name if name else f"<unnamed-{thread.ident}>"

    def get_running_resources(
        self, exclude_current: bool = True
    ) -> Set[threading.Thread]:
        """Get all currently running threads."""
        threads = set(threading.enumerate())

        if exclude_current:
            current = threading.current_thread()
            threads.discard(current)

        # Optionally exclude daemon threads (they're cleaned up automatically)
        if self.exclude_daemon:
            threads = {t for t in threads if not t.daemon}

        return threads

    def _is_resource_active(self, thread: threading.Thread) -> bool:
        """Check if a thread is still active/running."""
        return thread.is_alive()

    @property
    def leak_error_class(self) -> type:
        """Get the appropriate exception class for thread leaks."""
        return ThreadLeakError

    @property
    def resource_type(self) -> str:
        """Get the human-readable name for threads."""
        return "threads"

    def _handle_cancel_action(
        self, leaked_threads: List[threading.Thread], thread_names: List[str]
    ) -> None:
        """Handle the cancel action for leaked threads."""
        self.logger.warning(
            f"Cannot force-stop {len(leaked_threads)} leaked threads: {thread_names}. "
            "Consider using thread.join() or proper shutdown mechanisms."
        )


class _ThreadLeakContextManager(_BaseLeakContextManager):
    """Context manager that can also be used as a decorator."""

    def __init__(
        self,
        action: str = "warn",
        name_filter: Optional[Union[str, re.Pattern]] = DEFAULT_THREAD_NAME_FILTER,
        logger: Optional[logging.Logger] = _logger,
        exclude_daemon: bool = True,
        grace_period: float = 0.1,
    ):
        super().__init__(action, name_filter, logger)
        self.exclude_daemon = exclude_daemon
        self.grace_period = grace_period

    def _create_detector(self) -> _ThreadLeakDetector:
        """Create a thread leak detector instance."""
        return _ThreadLeakDetector(
            self.action, self.name_filter, self.logger, self.exclude_daemon
        )

    def _wait_for_completion(self) -> None:
        """Wait for threads to complete naturally."""
        time.sleep(self.grace_period)

    def __call__(self, func):
        """Allow this context manager to be used as a decorator."""

        def wrapper(*args, **kwargs):
            with self:
                return func(*args, **kwargs)

        return wrapper


def no_thread_leaks(
    action: str = "warn",
    name_filter: Optional[Union[str, re.Pattern]] = DEFAULT_THREAD_NAME_FILTER,
    logger: Optional[logging.Logger] = _logger,
    exclude_daemon: bool = True,
    grace_period: float = 0.1,
):
    """
    Context manager/decorator that detects thread leaks within its scope.

    Args:
        action: Action to take when leaks are detected ("warn", "log", "cancel", "raise")
        name_filter: Optional filter for thread names (string or regex)
        logger: Optional logger instance
        exclude_daemon: Whether to exclude daemon threads from detection
        grace_period: Time to wait for threads to finish naturally (seconds)

    Example:
        # As context manager
        with no_thread_leaks():
            threading.Thread(target=some_function).start()

        # As decorator
        @no_thread_leaks(action="raise")
        def my_function():
            threading.Thread(target=some_work).start()
    """
    return _ThreadLeakContextManager(
        action, name_filter, logger, exclude_daemon, grace_period
    )
