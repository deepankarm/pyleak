"""
Event Loop Block Detector

Detect when the asyncio event loop is blocked by synchronous operations.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import threading
import time
from typing import Any, List, Optional, Set

from pyleak.base import (
    LeakAction,
    LeakError,
    _BaseLeakContextManager,
    _BaseLeakDetector,
)
from pyleak.utils import setup_logger

_logger = setup_logger(__name__)


class EventLoopBlockError(LeakError):
    """Raised when event loop blocking is detected and action is set to RAISE."""

    pass


class _ThreadWithException(threading.Thread):
    """Thread that raises an exception when it finishes."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.exception = None

    def run(self):
        try:
            super().run()
        except Exception as e:
            self.exception = e


class _EventLoopBlockDetector(_BaseLeakDetector):
    """Core event loop blocking detection functionality."""

    def __init__(
        self,
        action: LeakAction = LeakAction.WARN,
        logger: Optional[logging.Logger] = _logger,
        *,
        threshold: float = 0.1,
        check_interval: float = 0.01,
        loop: asyncio.AbstractEventLoop | None = None,
    ):
        super().__init__(action=action, logger=logger)
        self.threshold = threshold
        self.check_interval = check_interval
        self.loop = loop or asyncio.get_running_loop()

        self.monitoring = False
        self.block_count = 0
        self.total_blocked_time = 0.0
        self.monitor_thread: Optional[_ThreadWithException] = None

    def _get_resource_name(self, _: Any) -> str:
        """Get block description."""
        return "event loop block"

    def get_running_resources(self, exclude_current: bool = True) -> Set[dict]:
        """Get current blocks (returns empty set as we track blocks differently)."""
        return set()

    def _is_resource_active(self, block_info: dict) -> bool:
        """Check if a block is still active (always False as blocks are instantaneous)."""
        return False

    @property
    def leak_error_class(self) -> type:
        """Get the appropriate exception class for event loop blocks."""
        return EventLoopBlockError

    @property
    def resource_type(self) -> str:
        """Get the human-readable name for event loop blocks."""
        return "event loop blocks"

    def _handle_cancel_action(
        self, leaked_resources: List[dict], resource_names: List[str]
    ) -> None:
        """Handle the cancel action for detected blocks (just warn as blocks can't be cancelled)."""
        self.logger.warning(
            f"Cannot cancel event loop blocks: {resource_names}. "
            "Consider using async alternatives to synchronous operations."
        )

    def start_monitoring(self):
        """Start monitoring the event loop for blocks."""

        self.monitoring = True
        self.monitor_thread = _ThreadWithException(
            target=self._monitor_loop, daemon=True
        )
        self.monitor_thread.start()

    def stop_monitoring(self):
        """Stop monitoring the event loop."""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=1.0)
            if self.monitor_thread.exception:
                raise self.monitor_thread.exception

    def _monitor_loop(self):
        """Monitor thread that checks event loop responsiveness."""
        while self.monitoring:
            start_time = time.perf_counter()
            future = asyncio.run_coroutine_threadsafe(
                self._ping_event_loop(), self.loop
            )
            try:
                future.result(timeout=self.threshold * 3)
                response_time = time.perf_counter() - start_time
                if response_time > self.threshold:
                    self._detect_block(response_time)

            except concurrent.futures.TimeoutError:
                response_time = time.perf_counter() - start_time
                self._detect_block(response_time)

            except Exception as e:
                self.logger.error(f"Event loop monitoring error: {e}", exc_info=True)

            time.sleep(self.check_interval)

    async def _ping_event_loop(self):
        """Simple coroutine to test event loop responsiveness."""
        return time.perf_counter()

    def _detect_block(self, duration: float) -> None:
        """Detect and handle a single blocking event."""
        self.block_count += 1
        self.total_blocked_time += duration
        self._handle_single_block(duration)

    def _handle_single_block(self, duration: float) -> None:
        """Handle a single detected block."""
        message = (
            f"Event loop blocked for {duration:.3f}s (threshold: {self.threshold:.3f}s)"
        )
        if self.action == "warn":
            import warnings

            warnings.warn(message, ResourceWarning, stacklevel=3)
        elif self.action == "log":
            self.logger.warning(message)
        elif self.action == "cancel":
            self.logger.warning(
                f"{message}. Cannot cancel blocking - consider using async alternatives."
            )
        elif self.action == "raise":
            raise EventLoopBlockError(message)

    def get_summary(self) -> dict:
        """Get summary of all detected blocks."""
        return {
            "total_blocks": self.block_count,
            "total_blocked_time": self.total_blocked_time,
        }


class _EventLoopBlockContextManager(_BaseLeakContextManager):
    """Context manager that can also be used as a decorator."""

    def __init__(
        self,
        action: LeakAction = LeakAction.WARN,
        logger: Optional[logging.Logger] = _logger,
        *,
        threshold: float = 0.1,
        check_interval: float = 0.01,
        loop: asyncio.AbstractEventLoop | None = None,
    ):
        super().__init__(action=action, logger=logger)
        self.threshold = threshold
        self.check_interval = check_interval
        self.loop = loop

    def _create_detector(self) -> _EventLoopBlockDetector:
        """Create an event loop block detector instance."""
        return _EventLoopBlockDetector(
            action=self.action,
            logger=self.logger,
            threshold=self.threshold,
            check_interval=self.check_interval,
            loop=self.loop,
        )

    def _wait_for_completion(self) -> None:
        """Wait for monitoring to complete (stop the monitor thread)."""
        pass

    def __enter__(self):
        self.detector = self._create_detector()
        self.initial_resources = set()  # Not used for event loop monitoring
        self.logger.debug("Starting event loop block monitoring")
        self.detector.start_monitoring()
        return self

    def __exit__(self, *args, **kwargs):
        self.detector.stop_monitoring()
        summary = self.detector.get_summary()
        if summary["total_blocks"] > 0:
            self.logger.debug(
                f"Event loop monitoring summary: {summary['total_blocks']} block(s), "
                f"{summary['total_blocked_time']:.2f}s total blocked time"
            )
        else:
            self.logger.debug("No event loop blocks detected")

    async def __aenter__(self):
        return self.__enter__()

    async def __aexit__(self, *args, **kwargs):
        self.__exit__(*args, **kwargs)

    def __call__(self, func):
        """Allow this context manager to be used as a decorator."""
        import functools

        print("func", func, "is async", asyncio.iscoroutinefunction(func))

        if not asyncio.iscoroutinefunction(func):
            raise ValueError(
                "no_event_loop_blocking can only be used with async functions"
            )

        @functools.wraps(func)
        async def sync_wrapper(*args, **kwargs):
            with self:
                return await func(*args, **kwargs)

        return sync_wrapper


def no_event_loop_blocking(
    action: LeakAction = LeakAction.WARN,
    logger: Optional[logging.Logger] = _logger,
    *,
    threshold: float = 0.2,
    check_interval: float = 0.05,
):
    """
    Context manager/decorator that detects event loop blocking within its scope.

    Args:
        threshold: Minimum blocking duration to report (seconds)
        action: Action to take when blocking is detected ("warn", "log", "cancel", "raise")
        name_filter: Optional filter for block names (string or regex)
        logger: Optional logger instance
        check_interval: How often to check for blocks (seconds)

    Example:
        # As context manager
        async def main():
            with no_event_loop_blocking(threshold=0.05):
                time.sleep(0.1)  # This will be detected

        # As decorator (works with both sync and async functions)
        @no_event_loop_blocking(action="raise")
        async def my_async_function():
            requests.get("https://example.com")  # Synchronous HTTP call

        @no_event_loop_blocking(action="warn")
        def my_sync_function():
            # Can also be used with sync functions that run in async context
            time.sleep(0.2)
    """
    return _EventLoopBlockContextManager(
        action=action,
        logger=logger,
        threshold=threshold,
        check_interval=check_interval,
    )
