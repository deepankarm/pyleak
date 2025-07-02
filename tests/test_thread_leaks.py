import asyncio
import re
import threading
import time
import uuid
import warnings
from typing import Optional
from unittest.mock import Mock

import pytest

from pyleak import ThreadLeakError, no_thread_leaks


def leaky_thread_function():
    """Function that creates a thread but doesn't join it."""

    def background_work():
        time.sleep(10)  # Long running work

    # Create thread but don't join it - this will leak!
    thread = threading.Thread(target=background_work)
    thread.start()
    time.sleep(0.1)  # Do some other work


def well_behaved_thread_function():
    """Function that properly manages its threads."""

    def background_work():
        time.sleep(0.1)

    thread = threading.Thread(target=background_work)
    thread.start()
    thread.join()  # Properly wait for thread


def create_named_thread(name: str):
    """Creates a named thread that will leak."""

    def background_work():
        time.sleep(10)

    thread = threading.Thread(target=background_work, name=name)
    thread.start()
    time.sleep(0.1)


def create_daemon_thread(name: str = "daemon-thread"):
    """Creates a daemon thread that will be excluded by default."""

    def background_work():
        time.sleep(10)

    thread = threading.Thread(target=background_work, name=name)
    thread.daemon = True
    thread.start()
    time.sleep(0.1)


def regular_sync_function():
    time.sleep(1)
    return "success"


class TestNoThreadLeaksContextManager:
    """Test no_thread_leaks when used as context manager."""

    def test_no_leaks_detected(self):
        """Test that no warnings are issued when no threads leak."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            with no_thread_leaks():
                well_behaved_thread_function()

            assert len(w) == 0

    def test_leak_detection_with_warning(self):
        """Test that leaked threads trigger warnings."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            with no_thread_leaks(action="warn"):
                leaky_thread_function()

            assert len(w) == 1
            assert issubclass(w[0].category, ResourceWarning)
            assert "leaked threads" in str(w[0].message)

    def test_leak_detection_with_exception(self):
        """Test that leaked threads can raise exceptions."""
        with pytest.raises(ThreadLeakError, match="leaked threads"):
            with no_thread_leaks(action="raise"):
                leaky_thread_function()

    def test_leak_detection_with_cancel_warning(self):
        """Test that CANCEL action warns about inability to stop threads."""
        leaked_thread: Optional[threading.Thread] = None

        def capture_leaked_thread():
            nonlocal leaked_thread

            def background_work():
                time.sleep(10)

            leaked_thread = threading.Thread(target=background_work)
            leaked_thread.start()
            time.sleep(0.1)

        mock_logger = Mock()
        with no_thread_leaks(action="cancel", logger=mock_logger):
            capture_leaked_thread()

        # Should warn that threads can't be force-stopped
        mock_logger.warning.assert_called_once()
        args = mock_logger.warning.call_args[0]
        assert "Cannot force-stop" in args[0]
        assert "leaked threads" in args[0]

    def test_logging_action(self):
        """Test that LOG action uses the logger."""
        mock_logger = Mock()

        with no_thread_leaks(action="log", logger=mock_logger):
            leaky_thread_function()

        mock_logger.warning.assert_called_once()
        args = mock_logger.warning.call_args[0]
        assert "leaked threads" in args[0]

    def test_name_filter_exact_match(self):
        """Test filtering threads by exact name match."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            with no_thread_leaks(action="warn", name_filter="target-thread"):
                # Create thread with matching name
                create_named_thread("target-thread")

                # Create thread with different name - should be ignored
                create_named_thread("other-thread")

            # Should only warn about the target thread
            assert len(w) == 1
            message = str(w[0].message)
            assert "target-thread" in message
            assert "other-thread" not in message

    def test_name_filter_regex(self):
        """Test filtering threads using regex patterns."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            some_id = str(uuid.uuid4())[:8]  # Use shorter ID for thread names
            pattern = re.compile(rf"{some_id}-\d+")
            with no_thread_leaks(action="warn", name_filter=pattern):
                # Create matching threads
                for i in range(1, 4):  # Fewer threads to avoid resource exhaustion
                    create_named_thread(f"{some_id}-{i}")

                # Create non-matching thread
                create_named_thread("manager-1")

            # Should warn about worker threads but not manager
            assert len(w) == 1
            message = str(w[0].message)
            for i in range(1, 4):
                assert f"{some_id}-{i}" in message
            assert "manager-1" not in message

    def test_exclude_daemon_threads_default(self):
        """Test that daemon threads are excluded by default."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            with no_thread_leaks(action="warn"):
                # Create daemon thread (should be ignored)
                create_daemon_thread()

            # Should not warn about daemon threads
            assert len(w) == 0

    def test_include_daemon_threads(self):
        """Test that daemon threads can be included in detection."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            with no_thread_leaks(action="warn", exclude_daemon=False):
                # Create daemon thread (should be detected)
                create_daemon_thread("test-daemon")

            # Should warn about daemon threads when not excluded
            assert len(w) == 1
            message = str(w[0].message)
            assert "leaked threads" in message
            assert "test-daemon" in message

    def test_grace_period_allows_completion(self):
        """Test that grace period allows threads to finish naturally."""

        def quick_work():
            time.sleep(0.05)  # Very short work

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            with no_thread_leaks(action="warn", grace_period=0.2):
                # Start thread that will complete during grace period
                thread = threading.Thread(target=quick_work)
                thread.start()
                # Don't join - let grace period handle it

            # Should not detect leak since thread completed during grace period
            assert len(w) == 0

    def test_grace_period_insufficient(self):
        """Test that insufficient grace period still detects leaks."""

        def medium_work():
            time.sleep(0.3)  # Work longer than grace period

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            with no_thread_leaks(action="warn", grace_period=0.05):
                # Start thread that won't complete during grace period
                thread = threading.Thread(target=medium_work)
                thread.start()

            # Should detect leak since thread didn't complete in time
            assert len(w) == 1
            assert "leaked threads" in str(w[0].message)

    def test_multiple_leaks(self):
        """Test detection of multiple leaked threads."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            with no_thread_leaks(action="warn"):
                # Create multiple leaks
                for i in range(3):

                    def work():
                        time.sleep(10)

                    thread = threading.Thread(target=work)
                    thread.start()
                time.sleep(0.1)

            assert len(w) == 1
            message = str(w[0].message)
            assert "3 leaked threads" in message

    def test_completed_threads_not_detected(self):
        """Test that completed threads are not considered leaks."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            with no_thread_leaks():
                # Create and complete a thread
                def quick_work():
                    time.sleep(0.01)

                thread = threading.Thread(target=quick_work)
                thread.start()
                thread.join()  # Wait for completion

            assert len(w) == 0


class TestNoThreadLeaksDecorator:
    """Test no_thread_leaks when used as decorator."""

    def test_decorator_no_leaks(self):
        """Test decorator works when no leaks occur."""

        @no_thread_leaks()
        def clean_function():
            well_behaved_thread_function()

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            clean_function()
            assert len(w) == 0

    def test_decorator_with_leaks(self):
        """Test decorator detects leaks."""

        @no_thread_leaks(action="warn")
        def leaky_decorated():
            leaky_thread_function()

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            leaky_decorated()
            assert len(w) == 1
            assert "leaked threads" in str(w[0].message)

    def test_decorator_with_return_value(self):
        """Test that decorator preserves return values."""

        @no_thread_leaks()
        def function_with_return():
            well_behaved_thread_function()
            return "success"

        result = function_with_return()
        assert result == "success"

    def test_decorator_with_arguments(self):
        """Test that decorator preserves function arguments."""

        @no_thread_leaks()
        def function_with_args(x, y, z=None):
            well_behaved_thread_function()
            return x + y + (z or 0)

        result = function_with_args(1, 2, z=3)
        assert result == 6

    def test_decorator_with_exception_handling(self):
        """Test that decorator properly handles exceptions from wrapped function."""

        @no_thread_leaks()
        def function_that_raises():
            well_behaved_thread_function()
            raise ValueError("test error")

        with pytest.raises(ValueError, match="test error"):
            function_that_raises()

    def test_decorator_with_name_filter(self):
        """Test decorator with name filtering."""

        @no_thread_leaks(action="warn", name_filter="filtered-thread")
        def function_with_filtered_leak():
            create_named_thread("filtered-thread")
            create_named_thread("unfiltered-thread")

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            function_with_filtered_leak()

        assert len(w) == 1
        message = str(w[0].message)
        assert "filtered-thread" in message
        assert "unfiltered-thread" not in message

    @pytest.mark.asyncio
    async def test_should_not_detect_asyncio_threads(self):
        """Test that asyncio threads created using `asyncio.to_thread` are not detected."""

        @no_thread_leaks(action="raise")
        async def async_function():
            return_value = await asyncio.to_thread(regular_sync_function)
            assert return_value == "success"

        await async_function()


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_empty_name_filter(self):
        """Test behavior with empty name filter."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            with no_thread_leaks(action="warn", name_filter=""):
                leaky_thread_function()

            # Empty string should not match anything
            assert len(w) == 0

    def test_invalid_regex_fallback(self):
        """Test that invalid regex falls back to string matching."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            # Use invalid regex pattern - should fall back to exact string match
            with no_thread_leaks(action="warn", name_filter="[invalid"):
                create_named_thread("[invalid")  # Exact match
                create_named_thread("other-thread")

            assert len(w) == 1
            message = str(w[0].message)
            assert "[invalid" in message
            assert "other-thread" not in message

    def test_unnamed_threads(self):
        """Test detection of unnamed threads."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            with no_thread_leaks(action="warn"):
                # Create unnamed thread
                def work():
                    time.sleep(10)

                thread = threading.Thread(target=work)
                thread.start()
                time.sleep(0.1)

            assert len(w) == 1
            message = str(w[0].message)
            # Should contain some representation of unnamed thread
            assert "leaked threads" in message

    def test_thread_completion_race_condition(self):
        """Test that threads completing during detection aren't flagged."""

        def very_quick_work():
            time.sleep(0.001)  # Very short work

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            with no_thread_leaks(grace_period=0.1):
                # Start thread that should complete during grace period
                thread = threading.Thread(target=very_quick_work)
                thread.start()
                # Give it time to start and complete
                time.sleep(0.05)

            # Should not detect leak since thread completed
            assert len(w) == 0

    def test_zero_grace_period(self):
        """Test behavior with zero grace period."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            with no_thread_leaks(action="warn", grace_period=0.0):
                leaky_thread_function()

            # Should still detect leaks even with no grace period
            assert len(w) == 1
            assert "leaked threads" in str(w[0].message)

    def test_main_thread_excluded(self):
        """Test that main thread is excluded from detection."""
        main_thread = threading.current_thread()

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            with no_thread_leaks(action="warn"):
                # Main thread should be excluded automatically
                pass

            # Should not warn about main thread
            assert len(w) == 0


@pytest.fixture(autouse=True)
def cleanup_leaked_threads():
    """Cleanup any threads that might have leaked during testing."""
    initial_threads = set(threading.enumerate())

    yield

    current_threads = set(threading.enumerate())
    new_threads = current_threads - initial_threads
    non_daemon_threads = [t for t in new_threads if t.is_alive() and not t.daemon]
    if non_daemon_threads:
        # Give threads a chance to finish naturally
        time.sleep(0.5)
        still_running = [t for t in non_daemon_threads if t.is_alive()]
        if still_running:
            print(f"{len(still_running)} thread(s) still running after test cleanup:")
            for thread in still_running:
                print(f"Thread {thread.name} is still running")
                # thread.join()
