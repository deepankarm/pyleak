"""
Event Loop Block Detector with Stack Trace Support

Detect when the asyncio event loop is blocked by synchronous operations
and capture stack traces showing exactly what's blocking.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import sys
import threading
import time
import traceback
from dataclasses import dataclass
from typing import Any, List, Optional, Set

from pyleak.base import (
    LeakAction,
    LeakError,
    _BaseLeakContextManager,
    _BaseLeakDetector,
)
from pyleak.utils import setup_logger

_logger = setup_logger(__name__)


@dataclass
class EventLoopBlock:
    """Information about an event loop blocking event."""

    block_id: int
    duration: float
    threshold: float
    timestamp: float
    blocking_stack: Optional[List[traceback.FrameSummary]] = None

    def format_blocking_stack(self) -> str:
        """Format the blocking stack trace as a string."""
        if not self.blocking_stack:
            return "No blocking stack available"

        return "".join(traceback.format_list(self.blocking_stack))

    def __str__(self) -> str:
        """String representation of the blocking event."""
        lines = [
            f"Event Loop Block: block-{self.block_id}",
            f"  Duration: {self.duration:.3f}s (threshold: {self.threshold:.3f}s)",
            f"  Timestamp: {self.timestamp:.3f}",
        ]

        if self.blocking_stack:
            lines.extend(
                [
                    "  Blocking Stack:",
                    "    "
                    + "\n    ".join(self.format_blocking_stack().strip().split("\n")),
                ]
            )

        return "\n".join(lines)


class EventLoopBlockError(LeakError):
    """Raised when event loop blocking is detected and action is set to RAISE."""

    def __init__(self, message: str, blocking_events: List[EventLoopBlock]):
        super().__init__(message)
        self.blocking_events = blocking_events
        self.block_count = len(blocking_events)

    def get_block_summary(self) -> str:
        """Get a summary of all blocking events."""
        return "\n".join(str(block) for block in self.blocking_events)

    def __str__(self) -> str:
        base_msg = super().__str__()
        return f"{base_msg}\n\n{self.get_block_summary()}"


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
    """Core event loop blocking detection functionality with stack trace support."""

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
        self.threshold_multiplier = 3
        self.block_count = 0
        self.total_blocked_time = 0.0
        self.monitor_thread: Optional[_ThreadWithException] = None
        self.main_thread_id = threading.get_ident()
        self.detected_blocks: List[EventLoopBlock] = []

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

    def _capture_main_thread_stack(self) -> Optional[List[traceback.FrameSummary]]:
        """Capture the current stack trace of the main thread."""
        try:
            if frame := sys._current_frames().get(self.main_thread_id):
                return traceback.extract_stack(frame)
        except Exception as e:
            self.logger.debug(f"Failed to capture main thread stack: {e}")

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
            self.monitor_thread.join(timeout=self.threshold)
            if self.monitor_thread.exception:
                raise self.monitor_thread.exception

    def _monitor_loop(self):
        """Monitor thread that checks event loop responsiveness."""
        while self.monitoring:
            start_time = time.time()
            future = asyncio.run_coroutine_threadsafe(
                self._ping_event_loop(), self.loop
            )
            try:
                future.result(timeout=self.threshold * self.threshold_multiplier)
                response_time = time.time() - start_time
                if response_time > self.threshold:
                    blocking_stack = self._capture_main_thread_stack()
                    self._detect_block(response_time, blocking_stack)

            except concurrent.futures.TimeoutError:
                response_time = time.time() - start_time
                blocking_stack = self._capture_main_thread_stack()
                self._detect_block(response_time, blocking_stack)

            except concurrent.futures.CancelledError:
                break

            except Exception as e:
                self.logger.error(f"Event loop monitoring error: {e}", exc_info=True)

            time.sleep(self.check_interval)

    async def _ping_event_loop(self):
        """Simple coroutine to test event loop responsiveness."""
        return time.perf_counter()

    def _detect_block(
        self,
        duration: float,
        blocking_stack: Optional[List[traceback.FrameSummary]] = None,
    ) -> None:
        """Detect and handle a single blocking event, combining consecutive identical blocks."""
        current_time = time.time()
        if self.detected_blocks and self._stacks_are_same(
            self.detected_blocks[-1].blocking_stack, blocking_stack
        ):
            last_block = self.detected_blocks[-1]
            last_block.duration += duration
            last_block.timestamp = current_time
            self.total_blocked_time += duration
        else:
            self.block_count += 1
            self.total_blocked_time += duration
            block_info = EventLoopBlock(
                block_id=self.block_count,
                duration=duration,
                threshold=self.threshold,
                timestamp=current_time,
                blocking_stack=blocking_stack,
            )

            self.detected_blocks.append(block_info)
            self._handle_single_block(block_info)

    def _stacks_are_same(
        self,
        stack1: list[traceback.FrameSummary] | None,
        stack2: list[traceback.FrameSummary] | None,
    ) -> bool:
        if stack1 is None and stack2 is None:
            return True
        if stack1 is None or stack2 is None:
            return False
        if len(stack1) != len(stack2):
            return False

        for frame1, frame2 in zip(stack1, stack2):
            if (
                frame1.filename != frame2.filename
                or frame1.lineno != frame2.lineno
                or frame1.name != frame2.name
            ):
                return False
        return True

    def handle_detected_blocks(self) -> None:
        """Handle all detected blocks at the end of monitoring (similar to handle_leaked_resources)."""
        if not self.detected_blocks:
            return

        message = f"Detected {len(self.detected_blocks)} event loop blocks"
        if self.action == "warn":
            import warnings

            warnings.warn(message, ResourceWarning, stacklevel=3)
            for block_info in self.detected_blocks:
                warnings.warn(str(block_info), ResourceWarning, stacklevel=4)
        elif self.action == "log":
            self.logger.warning(message)
            for block_info in self.detected_blocks:
                self.logger.warning(str(block_info))
        elif self.action == "cancel":
            self.logger.warning(
                f"{message}. Cannot cancel blocking - consider using async alternatives."
            )
            for block_info in self.detected_blocks:
                self.logger.warning(str(block_info))
        elif self.action == "raise":
            raise EventLoopBlockError(message, self.detected_blocks)

    def _handle_single_block(self, block_info: EventLoopBlock) -> None:
        """Handle a single detected block (immediate response)."""
        message = (
            f"Event loop blocked for {block_info.duration:.3f}s "
            f"(threshold: {block_info.threshold:.3f}s)"
        )

        # For immediate response modes, handle right away
        if self.action == "raise":
            # For raise, we accumulate and raise at the end like tasks
            pass  # Will be handled in handle_detected_blocks
        else:
            # For warn/log/cancel, provide immediate feedback
            if self.action == "warn":
                import warnings

                warnings.warn(message, ResourceWarning, stacklevel=5)
            elif self.action == "log":
                self.logger.warning(message)
            elif self.action == "cancel":
                self.logger.warning(
                    f"{message}. Cannot cancel blocking - consider using async alternatives."
                )

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
        self.detector.handle_detected_blocks()
        summary = self.detector.get_summary()
        if summary["total_blocks"] > 0:
            self.logger.warning(
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

        if not asyncio.iscoroutinefunction(func):
            raise ValueError(
                "no_event_loop_blocking can only be used with async functions"
            )

        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            with self:
                return await func(*args, **kwargs)

        return wrapper


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
        action: Action to take when blocking is detected
        logger: Optional logger instance
        threshold: Minimum blocking duration to report (seconds)
        check_interval: How often to check for blocks (seconds)
        capture_stacks: Whether to capture stack traces of blocking code

    Example:
        # Basic usage
        async def main():
            with no_event_loop_blocking(threshold=0.05):
                time.sleep(0.1)  # This will be detected with stack trace

        # Handle blocking with detailed stack information
        try:
            with no_event_loop_blocking(action="raise", capture_stacks=True):
                requests.get("https://httpbin.org/delay/1")  # Synchronous HTTP call
        except EventLoopBlockError as e:
            print(f"Event loop blocked for {e.duration:.3f}s")
            print("Blocking code:")
            print(e.block_info.format_blocking_stack())

        # As decorator
        @no_event_loop_blocking(action="raise")
        async def my_async_function():
            requests.get("https://example.com")  # Synchronous HTTP call
    """
    return _EventLoopBlockContextManager(
        action=action,
        logger=logger,
        threshold=threshold,
        check_interval=check_interval,
    )
