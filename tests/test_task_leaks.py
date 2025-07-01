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


async def function_with_exception():
    asyncio.create_task(asyncio.sleep(10))
    raise Exception("test")


class TestNoTaskLeaksContextManager:
    """Test no_task_leaks when used as context manager."""

    async def test_no_leaks_detected(self):
        """Test that no warnings are issued when no tasks leak."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            async with no_task_leaks():
                await well_behaved_function()

            assert len(w) == 0

    async def test_action_warn(self):
        """Test that leaked tasks trigger warnings."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            async with no_task_leaks(action="warn"):
                await leaky_function()

            assert len(w) == 2
            assert issubclass(w[0].category, ResourceWarning)
            assert "leaked asyncio tasks" in str(w[0].message)

            assert issubclass(w[1].category, ResourceWarning)
            assert "await asyncio.sleep(10)  # Long running task" in str(w[1].message)

    async def test_action_raise(self):
        """Test that leaked tasks can raise exceptions."""
        with pytest.raises(TaskLeakError, match="leaked asyncio tasks") as e:
            async with no_task_leaks(action="raise"):
                await leaky_function()

        assert "leaked asyncio tasks" in str(e.value)
        assert len(e.value.leaked_tasks) == 1
        assert e.value.leaked_tasks[0].name is not None
        assert e.value.leaked_tasks[0].state == "running"
        assert e.value.leaked_tasks[0].current_stack is not None
        assert e.value.leaked_tasks[0].creation_stack is None  # non debug mode
        assert e.value.leaked_tasks[0].task_ref is not None
        assert "await asyncio.sleep(10)  # Long running task" in str(e.value)

    async def test_action_cancel(self):
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

    async def test_action_log(self):
        """Test that LOG action uses the logger."""
        mock_logger = Mock()

        async with no_task_leaks(action="log", logger=mock_logger):
            await leaky_function()

        assert mock_logger.warning.call_count == 2
        assert "leaked asyncio tasks" in mock_logger.warning.call_args_list[0][0][0]
        assert (
            "await asyncio.sleep(10)  # Long running task"
            in mock_logger.warning.call_args_list[1][0][0]
        )

    async def test_name_filter_exact_match(self):
        """Test filtering tasks by exact name match."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            async with no_task_leaks(action="warn", name_filter="target-task"):
                # Create task with matching name
                await create_named_task("target-task")

                # Create task with different name - should be ignored
                await create_named_task("other-task")

            assert len(w) == 2
            assert "1 leaked asyncio tasks" in str(w[0].message)
            assert "target-task" in str(w[1].message)
            assert "other-task" not in str(w[0].message)

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

            assert len(w) == 10
            all_messages = "\n".join([str(warning.message) for warning in w])
            for i in range(1, 10):
                assert f"{some_id}-{i}" in all_messages
            assert "manager-1" not in all_messages

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

            assert len(w) == 4
            all_messages = "\n".join([str(warning.message) for warning in w])
            assert "3 leaked asyncio tasks" in all_messages

    async def test_invalid_regex_fallback(self):
        """Test that invalid regex falls back to string matching."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            # Use invalid regex pattern - should fall back to exact string match
            async with no_task_leaks(action="warn", name_filter="[invalid"):
                await create_named_task("[invalid")  # Exact match
                await create_named_task("other-task")

            assert len(w) == 2
            all_messages = "\n".join([str(warning.message) for warning in w])
            assert "[invalid" in all_messages
            assert "other-task" not in all_messages

    async def test_enable_creation_tracking_with_exception(self):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            with pytest.raises(Exception, match="test"):
                async with no_task_leaks(action="warn", enable_creation_tracking=True):
                    await function_with_exception()

            all_warnings = "\n".join([str(warning.message) for warning in w])
            assert len(w) == 2
            assert "asyncio.create_task(asyncio.sleep(10))" in all_warnings
            assert "test_task_leaks.py" in all_warnings

    async def test_enable_creation_tracking(self):
        """Test that enable_creation_tracking works."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            async with no_task_leaks(action="warn", enable_creation_tracking=True):
                await leaky_function()

            assert len(w) == 2
            assert "Creation Stack" in str(w[1].message)
            assert "test_task_leaks.py" in str(w[1].message)  # this file name
            assert "asyncio.create_task(background_task())" in str(w[1].message)


class TestNoTaskLeaksDecorator:
    """Test no_task_leaks when used as decorator."""

    async def test_no_leaks(self):
        """Test decorator works when no leaks occur."""

        @no_task_leaks()
        async def clean_function():
            await well_behaved_function()

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            await clean_function()
            assert len(w) == 0

    async def test_action_warn(self):
        """Test decorator detects leaks."""

        @no_task_leaks(action="warn")
        async def leaky_decorated():
            await leaky_function()

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            await leaky_decorated()
            assert len(w) == 2
            assert "leaked asyncio tasks" in str(w[0].message)
            assert "await asyncio.sleep(10)  # Long running task" in str(w[1].message)

    async def test_action_raise(self):
        """Test that decorator raises exceptions."""

        @no_task_leaks(action="raise", enable_creation_tracking=True)
        async def leaky_decorated():
            await leaky_function()

        with pytest.raises(TaskLeakError, match="leaked asyncio tasks") as e:
            await leaky_decorated()

        assert "leaked asyncio tasks" in str(e.value)
        assert len(e.value.leaked_tasks) == 1
        assert e.value.leaked_tasks[0].name is not None
        assert e.value.leaked_tasks[0].state == "running"
        assert e.value.leaked_tasks[0].current_stack is not None
        assert e.value.leaked_tasks[0].creation_stack is not None
        assert e.value.leaked_tasks[0].task_ref is not None
        assert "await asyncio.sleep(10)  # Long running task" in str(e.value)
        assert "Creation Stack" in str(e.value)
        assert "test_task_leaks.py" in str(e.value)
        assert "asyncio.create_task(background_task())" in str(e.value)

    async def test_decorator_with_name_filter(self):
        """Test decorator with name filtering."""

        @no_task_leaks(action="warn", name_filter="filtered-task")
        async def function_with_filtered_leak():
            await create_named_task("filtered-task")
            await create_named_task("unfiltered-task")

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            await function_with_filtered_leak()

        assert len(w) == 2
        all_messages = "\n".join([str(warning.message) for warning in w])
        assert "filtered-task" in all_messages
        assert "unfiltered-task" not in all_messages


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
