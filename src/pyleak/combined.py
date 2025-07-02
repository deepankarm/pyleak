from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any

from pyleak import (
    EventLoopBlockError,
    TaskLeakError,
    ThreadLeakError,
    no_event_loop_blocking,
    no_task_leaks,
    no_thread_leaks,
    DEFAULT_THREAD_NAME_FILTER,
)
from pyleak.base import PyleakExceptionGroup


@dataclass
class PyLeakConfig:
    """Configuration for pyleak detection"""

    tasks: bool = field(
        default=True, metadata={"description": "Whether to detect task leaks"}
    )
    task_action: str = field(
        default="raise",
        metadata={"description": "Action to take when a task leak is detected"},
    )
    task_name_filter: str | None = field(
        default=None, metadata={"description": "Filter to apply to task names"}
    )
    enable_task_creation_tracking: bool = field(
        default=False,
        metadata={"description": "Whether to enable task creation tracking"},
    )

    threads: bool = field(
        default=True, metadata={"description": "Whether to detect thread leaks"}
    )
    thread_action: str = field(
        default="raise",
        metadata={"description": "Action to take when a thread leak is detected"},
    )
    thread_name_filter: str | None = field(
        default=DEFAULT_THREAD_NAME_FILTER,
        metadata={
            "description": "Filter to apply to thread names (default: exclude asyncio threads)"
        },
    )
    exclude_daemon_threads: bool = field(
        default=True, metadata={"description": "Whether to exclude daemon threads"}
    )

    blocking: bool = field(
        default=True, metadata={"description": "Whether to detect event loop blocking"}
    )
    blocking_action: str = field(
        default="raise",
        metadata={
            "description": "Action to take when a blocking event loop is detected"
        },
    )
    blocking_threshold: float = field(
        default=0.2,
        metadata={"description": "Threshold for blocking event loop detection"},
    )
    blocking_check_interval: float = field(
        default=0.01,
        metadata={"description": "Interval for checking for blocking event loop"},
    )

    @classmethod
    def from_marker_args(cls, marker_args: dict[str, Any]):
        config = cls()
        config.tasks = marker_args.get("tasks", True)
        config.task_action = marker_args.get("task_action", "raise")
        config.task_name_filter = marker_args.get("task_name_filter", None)
        config.enable_task_creation_tracking = marker_args.get(
            "enable_task_creation_tracking", False
        )
        config.threads = marker_args.get("threads", True)
        config.thread_action = marker_args.get("thread_action", "raise")
        config.thread_name_filter = marker_args.get(
            "thread_name_filter", DEFAULT_THREAD_NAME_FILTER
        )
        config.exclude_daemon_threads = marker_args.get("exclude_daemon_threads", True)

        config.blocking = marker_args.get("blocking", True)
        config.blocking_action = marker_args.get("blocking_action", "raise")
        config.blocking_threshold = marker_args.get("blocking_threshold", 0.2)
        config.blocking_check_interval = marker_args.get(
            "blocking_check_interval", 0.01
        )
        return config

    def to_markdown_table(self) -> str:
        """Generate markdown table from the above args including names and default values"""
        markdown = "| Name | Default | Description |\n"
        markdown += "|:------|:------|:------|\n"
        for f in fields(self):
            markdown += (
                f"| {f.name} | {f.default} | {f.metadata.get('description', '')} |\n"
            )
        markdown += "\n"
        return markdown


class CombinedLeakDetector:
    def __init__(self, config: PyLeakConfig, is_async: bool):
        self.config = config
        self.is_async = is_async
        self.task_detector = None
        self.thread_detector = None
        self.blocking_detector = None

    async def __aenter__(self):
        if self.is_async and self.config.tasks:
            self.task_detector = no_task_leaks(
                action=self.config.task_action,
                name_filter=self.config.task_name_filter,
                enable_creation_tracking=self.config.enable_task_creation_tracking,
            )
            await self.task_detector.__aenter__()

        if self.is_async and self.config.blocking:
            self.blocking_detector = no_event_loop_blocking(
                action=self.config.blocking_action,
                threshold=self.config.blocking_threshold,
                check_interval=self.config.blocking_check_interval,
            )
            self.blocking_detector.__enter__()

        if self.config.threads:
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
        if self.config.threads:
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
            try:
                self.thread_detector.__exit__(exc_type, exc_val, exc_tb)
            except ThreadLeakError as e:
                raise PyleakExceptionGroup(
                    "PyLeak detected issues:\n" + "\n\n".join([str(e) for e in [e]]),
                    [e],
                )
