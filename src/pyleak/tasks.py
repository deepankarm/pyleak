"""
AsyncIO Task Leak Detector

A Python library for detecting and handling leaked asyncio tasks,
inspired by Go's goleak package.
"""

import asyncio
import logging
import re
from functools import wraps
from typing import List, Optional, Set, Union

from pyleak.base import (
    LeakAction,
    LeakError,
    _BaseLeakContextManager,
    _BaseLeakDetector,
)
from pyleak.utils import setup_logger

_logger = setup_logger(__name__)


class TaskLeakError(LeakError):
    """Raised when task leaks are detected and action is set to RAISE."""

    pass


class _TaskLeakDetector(_BaseLeakDetector):
    """Core task leak detection functionality."""

    def _get_resource_name(self, task: asyncio.Task) -> str:
        """Get task name, handling both named and unnamed tasks."""
        name = getattr(task, "_name", None) or task.get_name()
        return name if name else f"<unnamed-{id(task)}>"

    def get_running_resources(self, exclude_current: bool = True) -> Set[asyncio.Task]:
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

    def _is_resource_active(self, task: asyncio.Task) -> bool:
        """Check if a task is still active/running."""
        return not task.done()

    @property
    def leak_error_class(self) -> type:
        """Get the appropriate exception class for task leaks."""
        return TaskLeakError

    @property
    def resource_type(self) -> str:
        """Get the human-readable name for tasks."""
        return "asyncio tasks"

    def _handle_cancel_action(
        self, leaked_tasks: List[asyncio.Task], task_names: List[str]
    ) -> None:
        """Handle the cancel action for leaked tasks."""
        self.logger.debug(f"Cancelling {len(leaked_tasks)} leaked tasks: {task_names}")
        for task in leaked_tasks:
            if not task.done():
                task.cancel()


class _AsyncTaskLeakContextManager(_BaseLeakContextManager):
    """Async context manager that can also be used as a decorator."""

    def _create_detector(self) -> _TaskLeakDetector:
        """Create a task leak detector instance."""
        return _TaskLeakDetector(self.action, self.name_filter, self.logger)

    async def _wait_for_completion(self) -> None:
        """Wait for tasks to complete naturally."""
        await asyncio.sleep(0.01)

    async def __aenter__(self):
        return self._enter_context()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self._wait_for_completion()
        leaked_resources = self.detector.get_leaked_resources(self.initial_resources)
        self.logger.debug(f"Detected {len(leaked_resources)} leaked asyncio tasks")
        self.detector.handle_leaked_resources(leaked_resources)

    def __call__(self, func):
        """Allow this context manager to be used as a decorator."""

        @wraps(func)
        async def wrapper(*args, **kwargs):
            async with self:
                return await func(*args, **kwargs)

        return wrapper


def no_task_leaks(
    action: Union[LeakAction, str] = LeakAction.WARN,
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
    # Convert enum to string if needed
    if isinstance(action, LeakAction):
        action = action.value

    return _AsyncTaskLeakContextManager(action, name_filter, logger)
