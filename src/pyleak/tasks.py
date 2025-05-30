"""
AsyncIO Task Leak Detector

A Python library for detecting and handling leaked asyncio tasks,
inspired by Go's goleak package.
"""

import asyncio
import logging
import re
import warnings
from enum import Enum
from functools import wraps
from typing import List, Optional, Set, Union

from pyleak.utils import setup_logger

_logger = setup_logger(__name__)


class LeakAction(str, Enum):
    """Actions to take when task leaks are detected."""

    WARN = "warn"
    LOG = "log"
    CANCEL = "cancel"
    RAISE = "raise"


class TaskLeakError(Exception):
    """Raised when task leaks are detected and action is set to RAISE."""

    pass


class _TaskLeakDetector:
    """Core task leak detection functionality."""

    def __init__(
        self,
        action: LeakAction = LeakAction.WARN,
        name_filter: Optional[Union[str, re.Pattern]] = None,
        logger: Optional[logging.Logger] = _logger,
    ):
        self.action = action
        self.name_filter = name_filter
        self.logger = logger

    def _matches_filter(self, task_name: str) -> bool:
        """Check if task name matches the filter."""
        if self.name_filter is None:
            return True

        if isinstance(self.name_filter, str):
            return task_name == self.name_filter
        elif isinstance(self.name_filter, re.Pattern):
            return bool(self.name_filter.search(task_name))
        else:
            # Try to compile as regex if it's a string-like pattern
            try:
                pattern = re.compile(str(self.name_filter))
                return bool(pattern.search(task_name))
            except re.error:
                return task_name == str(self.name_filter)

    def _get_task_name(self, task: asyncio.Task) -> str:
        """Get task name, handling both named and unnamed tasks."""
        name = getattr(task, "_name", None) or task.get_name()
        return name if name else f"<unnamed-{id(task)}>"

    def get_running_tasks(self, exclude_current: bool = True) -> Set[asyncio.Task]:
        """Get all currently running tasks."""
        tasks = asyncio.all_tasks()

        if exclude_current:
            try:
                current = asyncio.current_task()
                tasks.discard(current)
            except RuntimeError:
                # No current task (not in async context)
                pass

        return tasks

    def get_leaked_tasks(self, initial_tasks: Set[asyncio.Task]) -> List[asyncio.Task]:
        """Find tasks that are still running and match the filter."""
        current_tasks = self.get_running_tasks()
        new_tasks = current_tasks - initial_tasks

        leaked_tasks = []
        for task in new_tasks:
            if not task.done():
                task_name = self._get_task_name(task)
                if self._matches_filter(task_name):
                    leaked_tasks.append(task)

        return leaked_tasks

    def handle_leaked_tasks(self, leaked_tasks: List[asyncio.Task]) -> None:
        """Handle detected leaked tasks based on the configured action."""
        if not leaked_tasks:
            return

        task_names = [self._get_task_name(task) for task in leaked_tasks]
        message = f"Detected {len(leaked_tasks)} leaked asyncio tasks: {task_names}"

        if self.action == LeakAction.WARN:
            warnings.warn(message, ResourceWarning, stacklevel=3)
        elif self.action == LeakAction.LOG:
            self.logger.warning(message)
        elif self.action == LeakAction.CANCEL:
            self.logger.info(
                f"Cancelling {len(leaked_tasks)} leaked tasks: {task_names}"
            )
            for task in leaked_tasks:
                if not task.done():
                    task.cancel()
        elif self.action == LeakAction.RAISE:
            raise TaskLeakError(message)


class _AsyncTaskLeakContextManager:
    """Async context manager that can also be used as a decorator."""

    def __init__(
        self,
        action: LeakAction = LeakAction.WARN,
        name_filter: Optional[Union[str, re.Pattern]] = None,
        logger: Optional[logging.Logger] = _logger,
    ):
        self.action = action
        self.name_filter = name_filter
        self.logger = logger

    async def __aenter__(self):
        self.detector = _TaskLeakDetector(self.action, self.name_filter, self.logger)
        self.initial_tasks = self.detector.get_running_tasks()
        self.logger.debug(f"Detected {len(self.initial_tasks)} initial tasks")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # Small delay to allow tasks to complete
        await asyncio.sleep(0.01)
        leaked_tasks = self.detector.get_leaked_tasks(self.initial_tasks)
        self.logger.debug(f"Detected {len(leaked_tasks)} leaked tasks")
        self.detector.handle_leaked_tasks(leaked_tasks)

    def __call__(self, func):
        """Allow this context manager to be used as a decorator."""

        @wraps(func)
        async def wrapper(*args, **kwargs):
            async with self:
                return await func(*args, **kwargs)

        return wrapper


def no_task_leaks(
    action: LeakAction = LeakAction.WARN,
    name_filter: Optional[Union[str, re.Pattern]] = None,
    logger: Optional[logging.Logger] = _logger,
):
    """
    Context manager/decorator that detects task leaks within its scope.

    Args:
        action: Action to take when leaks are detected
        name_filter: Optional filter for task names (string or regex)
        logger: Optional logger instance

    Example:
        # As context manager
        async with no_task_leaks():
            await some_async_function()

        # As decorator
        @no_task_leaks(action=LeakAction.LOG)
        async def my_function():
            await some_async_function()
    """
    return _AsyncTaskLeakContextManager(action, name_filter, logger)
