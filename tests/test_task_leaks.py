import asyncio
import re
import uuid
import warnings
from typing import Optional
from unittest.mock import Mock

import pytest
import pytest_asyncio

from pyleak import TaskLeakError, no_task_leaks

pytestmark = pytest.mark.asyncio


async def leaky_function():
    """Function that creates a task but doesn't await it."""

    async def background_task():
        await asyncio.sleep(10)  # Long running task

    # Create task but don't await it - this will leak!
    asyncio.create_task(background_task())
    await asyncio.sleep(0.1)  # Do some other work


async def well_behaved_function():
    """Function that properly manages its tasks."""

    async def background_task():
        await asyncio.sleep(0.1)

    task = asyncio.create_task(background_task())
    await task  # Properly await the task


async def create_named_task(name: str):
    """Creates a named task that will leak."""
    asyncio.create_task(asyncio.sleep(10), name=name)
    await asyncio.sleep(0.1)


class TestNoTaskLeaksContextManager:
    """Test no_task_leaks when used as context manager."""

    async def test_no_leaks_detected(self):
        """Test that no warnings are issued when no tasks leak."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            async with no_task_leaks():
                await well_behaved_function()

            assert len(w) == 0

    async def test_leak_detection_with_warning(self):
        """Test that leaked tasks trigger warnings."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            async with no_task_leaks(action="warn"):
                await leaky_function()

            assert len(w) == 1
            assert issubclass(w[0].category, ResourceWarning)
            assert "leaked asyncio tasks" in str(w[0].message)

    async def test_leak_detection_with_exception(self):
        """Test that leaked tasks can raise exceptions."""
        with pytest.raises(TaskLeakError, match="leaked asyncio tasks"):
            async with no_task_leaks(action="raise"):
                await leaky_function()

    async def test_leak_detection_with_cancel(self):
        """Test that leaked tasks can be cancelled."""
        leaked_task: Optional[asyncio.Task] = None

        async def capture_leaked_task():
            nonlocal leaked_task
            leaked_task = asyncio.create_task(asyncio.sleep(10))
            await asyncio.sleep(0.1)

        async with no_task_leaks(action="cancel"):
            await capture_leaked_task()

        # Give time for cancellation to take effect
        await asyncio.sleep(0.01)

        assert leaked_task is not None
        assert leaked_task.cancelled()

    async def test_logging_action(self):
        """Test that LOG action uses the logger."""
        mock_logger = Mock()

        async with no_task_leaks(action="log", logger=mock_logger):
            await leaky_function()

        mock_logger.warning.assert_called_once()
        args = mock_logger.warning.call_args[0]
        assert "leaked asyncio tasks" in args[0]

    async def test_name_filter_exact_match(self):
        """Test filtering tasks by exact name match."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            async with no_task_leaks(action="warn", name_filter="target-task"):
                # Create task with matching name
                await create_named_task("target-task")

                # Create task with different name - should be ignored
                await create_named_task("other-task")

            # Should only warn about the target task
            assert len(w) == 1
            message = str(w[0].message)
            assert "target-task" in message
            assert "other-task" not in message

    async def test_name_filter_regex(self):
        """Test filtering tasks using regex patterns."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            some_id = str(uuid.uuid4())
            pattern = re.compile(rf"{some_id}-\d+")
            async with no_task_leaks(action="warn", name_filter=pattern):
                for i in range(1, 10):
                    await create_named_task(f"{some_id}-{i}")

                await create_named_task("manager-1")

            assert len(w) == 1
            message = str(w[0].message)
            for i in range(1, 10):
                assert f"{some_id}-{i}" in message
            assert "manager-1" not in message

    async def test_completed_tasks_not_detected(self):
        """Test that completed tasks are not considered leaks."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            async with no_task_leaks():
                # Create and complete a task
                task = asyncio.create_task(asyncio.sleep(0.001))
                await task  # Wait for completion

            assert len(w) == 0

    async def test_multiple_leaks(self):
        """Test detection of multiple leaked tasks."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            async with no_task_leaks(action="warn"):
                # Create multiple leaks
                asyncio.create_task(asyncio.sleep(10))
                asyncio.create_task(asyncio.sleep(10))
                asyncio.create_task(asyncio.sleep(10))
                await asyncio.sleep(0.1)

            assert len(w) == 1
            message = str(w[0].message)
            assert "3 leaked asyncio tasks" in message


class TestNoTaskLeaksDecorator:
    """Test no_task_leaks when used as decorator."""

    async def test_decorator_no_leaks(self):
        """Test decorator works when no leaks occur."""

        @no_task_leaks()
        async def clean_function():
            await well_behaved_function()

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            await clean_function()
            assert len(w) == 0

    async def test_decorator_with_leaks(self):
        """Test decorator detects leaks."""

        @no_task_leaks(action="warn")
        async def leaky_decorated():
            await leaky_function()

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            await leaky_decorated()
            assert len(w) == 1
            assert "leaked asyncio tasks" in str(w[0].message)

    async def test_decorator_with_return_value(self):
        """Test that decorator preserves return values."""

        @no_task_leaks()
        async def function_with_return():
            await well_behaved_function()
            return "success"

        result = await function_with_return()
        assert result == "success"

    async def test_decorator_with_arguments(self):
        """Test that decorator preserves function arguments."""

        @no_task_leaks()
        async def function_with_args(x, y, z=None):
            await well_behaved_function()
            return x + y + (z or 0)

        result = await function_with_args(1, 2, z=3)
        assert result == 6

    async def test_decorator_with_exception_handling(self):
        """Test that decorator properly handles exceptions from wrapped function."""

        @no_task_leaks()
        async def function_that_raises():
            await well_behaved_function()
            raise ValueError("test error")

        with pytest.raises(ValueError, match="test error"):
            await function_that_raises()

    async def test_decorator_with_name_filter(self):
        """Test decorator with name filtering."""

        @no_task_leaks(action="warn", name_filter="filtered-task")
        async def function_with_filtered_leak():
            await create_named_task("filtered-task")
            await create_named_task("unfiltered-task")

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            await function_with_filtered_leak()

        assert len(w) == 1
        message = str(w[0].message)
        assert "filtered-task" in message
        assert "unfiltered-task" not in message


class TestEdgeCases:
    """Test edge cases and error conditions."""

    async def test_no_current_task_context(self):
        """Test behavior when there's no current running task."""
        # This shouldn't crash even if called outside normal async context
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            async with no_task_leaks():
                await asyncio.sleep(0.01)

            assert len(w) == 0

    async def test_empty_name_filter(self):
        """Test behavior with empty name filter."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            async with no_task_leaks(action="warn", name_filter=""):
                await leaky_function()

            # Empty string should not match anything
            assert len(w) == 0

    async def test_invalid_regex_fallback(self):
        """Test that invalid regex falls back to string matching."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            # Use invalid regex pattern - should fall back to exact string match
            async with no_task_leaks(action="warn", name_filter="[invalid"):
                await create_named_task("[invalid")  # Exact match
                await create_named_task("other-task")

            assert len(w) == 1
            message = str(w[0].message)
            assert "[invalid" in message
            assert "other-task" not in message

    async def test_unnamed_tasks(self):
        """Test detection of unnamed tasks."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            async with no_task_leaks(action="warn"):
                # Create unnamed task
                asyncio.create_task(asyncio.sleep(10))
                await asyncio.sleep(0.1)

            assert len(w) == 1
            message = str(w[0].message)
            # Should contain some representation of unnamed task
            assert "leaked asyncio tasks" in message

    async def test_task_completion_race_condition(self):
        """Test that tasks completing during detection aren't flagged."""

        async def quick_task():
            await asyncio.sleep(0.001)  # Very short task

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            async with no_task_leaks():
                # Start task but it might complete during the detection window
                task = asyncio.create_task(quick_task())  # noqa: F841
                await asyncio.sleep(0.005)  # Let it complete

            # Should not detect leak since task completed
            assert len(w) == 0


@pytest_asyncio.fixture(autouse=True)
async def cleanup_leaked_tasks():
    """Cleanup any tasks that might have leaked during testing."""
    yield

    # Cancel any remaining tasks to avoid interfering with other tests
    tasks = set([t for t in asyncio.all_tasks() if not t.done()])
    current_task = None
    try:
        current_task = asyncio.current_task()
    except RuntimeError:
        pass

    tasks.discard(current_task)
    for task in tasks:
        if not task.done():
            task.cancel()

    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
