from typing import Any

from pyleak import (
    EventLoopBlockError,
    TaskLeakError,
    ThreadLeakError,
    no_event_loop_blocking,
    no_task_leaks,
    no_thread_leaks,
)
from pyleak.base import PyleakExceptionGroup


class PyLeakConfig:
    """Configuration for pyleak detection"""

    def __init__(self, marker_args: dict[str, Any]):
        self.detect_tasks = marker_args.get("tasks", True)
        self.task_action = marker_args.get("task_action", "raise")
        self.task_name_filter = marker_args.get("task_name_filter", None)
        self.enable_task_creation_tracking = marker_args.get(
            "enable_creation_tracking", False
        )

        self.detect_threads = marker_args.get("threads", True)
        self.thread_action = marker_args.get("thread_action", "raise")
        self.thread_name_filter = marker_args.get("thread_name_filter", None)
        self.exclude_daemon_threads = marker_args.get("exclude_daemon", True)

        self.detect_blocking = marker_args.get("blocking", True)
        self.blocking_action = marker_args.get("blocking_action", "raise")
        self.blocking_threshold = marker_args.get("blocking_threshold", 0.1)
        self.blocking_check_interval = marker_args.get("blocking_check_interval", 0.01)


class CombinedLeakDetector:
    def __init__(self, config: PyLeakConfig, is_async: bool):
        self.config = config
        self.is_async = is_async
        self.task_detector = None
        self.thread_detector = None
        self.blocking_detector = None

    async def __aenter__(self):
        if self.is_async and self.config.detect_tasks:
            self.task_detector = no_task_leaks(
                action=self.config.task_action,
                name_filter=self.config.task_name_filter,
                enable_creation_tracking=self.config.enable_task_creation_tracking,
            )
            await self.task_detector.__aenter__()

        if self.is_async and self.config.detect_blocking:
            self.blocking_detector = no_event_loop_blocking(
                action=self.config.blocking_action,
                threshold=self.config.blocking_threshold,
                check_interval=self.config.blocking_check_interval,
            )
            self.blocking_detector.__enter__()

        if self.config.detect_threads:
            self.thread_detector = no_thread_leaks(
                action=self.config.thread_action,
                name_filter=self.config.thread_name_filter,
                exclude_daemon=self.config.exclude_daemon_threads,
            )
            self.thread_detector.__enter__()

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        leak_errors = []
        if self.thread_detector:
            try:
                self.thread_detector.__exit__(exc_type, exc_val, exc_tb)
            except ThreadLeakError as e:
                leak_errors.append(e)

        if self.blocking_detector:
            try:
                self.blocking_detector.__exit__(exc_type, exc_val, exc_tb)
            except EventLoopBlockError as e:
                leak_errors.append(e)

        if self.task_detector:
            try:
                await self.task_detector.__aexit__(exc_type, exc_val, exc_tb)
            except TaskLeakError as e:
                leak_errors.append(e)

        if leak_errors:
            raise PyleakExceptionGroup(
                "PyLeak detected issues:\n"
                + "\n\n".join([str(e) for e in leak_errors]),
                leak_errors,
            )

    def __enter__(self):
        if self.config.detect_threads:
            self.thread_detector = no_thread_leaks(
                action=self.config.thread_action,
                name_filter=self.config.thread_name_filter,
                exclude_daemon=self.config.exclude_daemon_threads,
            )
            self.thread_detector.__enter__()

        # Ignore `detect_tasks` and `detect_blocking` for sync tests
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.thread_detector:
            self.thread_detector.__exit__(exc_type, exc_val, exc_tb)
