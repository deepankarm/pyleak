"""
AsyncIO Task Leak Detector

A Python library for detecting and handling leaked asyncio tasks,
inspired by Go's goleak package.
"""

import asyncio
import logging
import re
import traceback
import warnings
from dataclasses import dataclass
from enum import Enum
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


class TaskState(str, Enum):
    """State of an asyncio task."""

    RUNNING = "running"
    CANCELLED = "cancelled"
    DONE = "done"


@dataclass
class LeakedTask:
    """Information about a leaked asyncio task."""

    task_id: int
    name: str
    state: TaskState
    current_stack: Optional[List[traceback.FrameSummary]] = None
    creation_stack: Optional[List[traceback.FrameSummary]] = None
    task_ref: Optional[asyncio.Task] = None

    @classmethod
    def from_task(cls, task: asyncio.Task) -> "LeakedTask":
        """Create a LeakedTask object from an asyncio.Task."""
        if task.cancelled():
            state = TaskState.CANCELLED
        elif task.done():
            state = TaskState.DONE
        else:
            state = TaskState.RUNNING

        return cls(
            task_id=id(task),
            name=task.get_name(),
            state=state,
            current_stack=_TaskStackCapture.capture_current_stack(task),
            creation_stack=_TaskStackCapture.get_task_creation_stack(task),
            task_ref=task,
        )

    def format_current_stack(self) -> str:
        """Format the current stack trace as a string."""
        if not self.current_stack:
            return "No current stack available"

        return "".join(traceback.format_list(self.current_stack))

    def format_creation_stack(self) -> str:
        """Format the creation stack trace as a string."""
        if not self.creation_stack:
            return "No creation stack available"

        return "".join(traceback.format_list(self.creation_stack))

    def __str__(self) -> str:
        """String representation of the leaked task."""
        lines = [
            f"Leaked Task: {self.name}",
            f"  ID: {self.task_id}",
            f"  State: {self.state}",
        ]

        if self.current_stack:
            lines.extend(
                [
                    "  Current Stack:",
                    "    "
                    + "\n    ".join(self.format_current_stack().strip().split("\n")),
                ]
            )

        if self.creation_stack:
            lines.extend(
                [
                    "  Creation Stack:",
                    "    "
                    + "\n    ".join(self.format_creation_stack().strip().split("\n")),
                ]
            )

        return "\n".join(lines)


class TaskLeakError(LeakError):
    """Raised when task leaks are detected and action is set to RAISE."""

    def __init__(self, message: str, leaked_tasks: List[LeakedTask]):
        super().__init__(message)
        self.leaked_tasks = leaked_tasks
        self.task_count = len(leaked_tasks)

    def get_stack_summary(self) -> str:
        """Get a summary of all stack traces."""
        return "\n".join(str(task) for task in self.leaked_tasks)

    def __str__(self) -> str:
        base_msg = super().__str__()
        return f"{base_msg}\n\n{self.get_stack_summary()}"


class _TaskStackCapture:
    """Utility class for capturing task stack traces."""

    @staticmethod
    def capture_current_stack(
        task: asyncio.Task,
    ) -> Optional[List[traceback.FrameSummary]]:
        """Capture current stack of a task using task.get_stack()."""
        try:
            frames = task.get_stack()
            if not frames:
                return None

            stack_summary = []
            for frame in frames:
                try:
                    stack_summary.append(
                        traceback.FrameSummary(
                            filename=frame.f_code.co_filename,
                            lineno=frame.f_lineno,
                            name=frame.f_code.co_name,
                        )
                    )
                except Exception:
                    continue

            return stack_summary

        except Exception:
            return None

    @staticmethod
    def capture_creation_stack() -> List[traceback.FrameSummary]:
        """Capture current stack as creation stack (call this when creating tasks)."""
        return traceback.extract_stack()[:-2]

    @staticmethod
    def get_task_creation_stack(
        task: asyncio.Task,
    ) -> Optional[List[traceback.FrameSummary]]:
        """Get the creation stack for a task if available."""
        try:
            if hasattr(task, "_source_traceback") and task._source_traceback:
                return task._source_traceback
        except Exception:
            pass

        return None


class _TaskLeakDetector(_BaseLeakDetector):
    """Core task leak detection functionality with stack trace support."""

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

    def handle_leaked_resources(self, leaked_resources: List[asyncio.Task]) -> None:
        """Handle leaked resources with detailed stack information."""
        if not leaked_resources:
            return

        task_names = [self._get_resource_name(task) for task in leaked_resources]
        leaked_task_infos = [LeakedTask.from_task(task) for task in leaked_resources]
        message = f"Detected {len(leaked_resources)} leaked {self.resource_type}"
        if self.action == "warn":
            warnings.warn(message, ResourceWarning, stacklevel=3)
            for task_info in leaked_task_infos:
                warnings.warn(str(task_info), ResourceWarning, stacklevel=4)
        elif self.action == "log":
            self.logger.warning(message)
            for task_info in leaked_task_infos:
                self.logger.warning(str(task_info))
        elif self.action == "cancel":
            self._handle_cancel_action(leaked_resources, task_names)
        elif self.action == "raise":
            raise TaskLeakError(message, leaked_task_infos)

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

    def __init__(
        self, action, name_filter=None, logger=None, enable_creation_tracking=False
    ):
        super().__init__(action, name_filter, logger)
        self.enable_creation_tracking = enable_creation_tracking
        self._original_loop_params = {
            "debug": False,
            "slow_callback_duration": 0.1,
        }

    def _create_detector(self) -> _TaskLeakDetector:
        """Create a task leak detector instance."""
        return _TaskLeakDetector(self.action, self.name_filter, self.logger)

    def enable_task_creation_tracking(self):
        """Enable automatic tracking of task creation stacks."""
        loop = asyncio.get_running_loop()
        self._original_loop_params["debug"] = loop.get_debug()
        self._original_loop_params["slow_callback_duration"] = (
            loop.slow_callback_duration
        )
        loop.set_debug(True)
        loop.slow_callback_duration = 10
        self.logger.debug("Debug mode enabled for task creation tracking")

    def disable_task_creation_tracking(self):
        """Disable task creation tracking."""
        loop = asyncio.get_running_loop()
        loop.set_debug(self._original_loop_params["debug"])
        loop.slow_callback_duration = self._original_loop_params[
            "slow_callback_duration"
        ]
        self.logger.debug("Debug mode disabled for task creation tracking")

    async def _wait_for_completion(self) -> None:
        """Wait for tasks to complete naturally."""
        await asyncio.sleep(0.01)

    async def __aenter__(self):
        if self.enable_creation_tracking:
            self.enable_task_creation_tracking()
        return self._enter_context()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self._wait_for_completion()
        leaked_resources = self.detector.get_leaked_resources(self.initial_resources)
        self.logger.debug(f"Detected {len(leaked_resources)} leaked asyncio tasks")
        self.detector.handle_leaked_resources(leaked_resources)
        if self.enable_creation_tracking:
            self.disable_task_creation_tracking()

    def __enter__(self):
        raise RuntimeError(
            "no_task_leaks cannot be used as a sync context manager, please use async with"
        )

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
    *,
    enable_creation_tracking: bool = False,
):
    """
    Context manager/decorator that detects task leaks within its scope.

    Args:
        action: Action to take when leaks are detected
        name_filter: Optional filter for task names (string or regex)
        logger: Optional logger instance
        enable_creation_tracking: Whether to enable automatic task creation tracking

    Example:
        # As context manager
        async with no_task_leaks():
            await some_async_function()

        # As decorator
        @no_task_leaks
        async def my_function():
            await some_async_function()

        # Handle the exception with full stack traces
        try:
            async with no_task_leaks(action=LeakAction.RAISE):
                # Code that leaks tasks
                pass
        except TaskLeakError as e:
            print(f"Found {e.task_count} leaked tasks")
            # Cancel leaked tasks
            for task_info in e.leaked_tasks:
                if task_info.task_ref and not task_info.task_ref.done():
                    task_info.task_ref.cancel()

    """
    return _AsyncTaskLeakContextManager(
        action, name_filter, logger, enable_creation_tracking
    )
