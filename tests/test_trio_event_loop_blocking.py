import time
import warnings

import pytest
import sniffio
import trio

from pyleak import EventLoopBlockError, no_event_loop_blocking


def _assert_trio():
    assert sniffio.current_async_library() == "trio"


@no_event_loop_blocking(action="warn")
async def bad_sleep_with_warning():
    time.sleep(1)


@no_event_loop_blocking(action="raise")
async def bad_sleep_with_exception():
    time.sleep(1)


@no_event_loop_blocking(action="warn")
async def good_sleep_with_warning():
    await trio.sleep(1)


class TestTrioEventLoopBlockingDecorator:
    @pytest.mark.trio
    async def test_no_blocking(self):
        """Test that no warnings are issued when no event loop blocking is detected."""
        _assert_trio()
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            await good_sleep_with_warning()
            assert len(w) == 0

    @pytest.mark.trio
    async def test_action_warning(self):
        """Test that event loop blocking triggers warnings."""
        _assert_trio()
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            await bad_sleep_with_warning()
            assert len(w) == 3
            assert issubclass(w[0].category, ResourceWarning)
            assert "Event loop blocked for" in str(w[0].message)
            assert "Detected 1 event loop blocks" in str(w[1].message)
            assert "bad_sleep_with_warning" in str(w[2].message)
            assert "time.sleep(1)" in str(w[2].message)

    @pytest.mark.trio
    async def test_action_raise(self):
        """Test that event loop blocking triggers exceptions."""
        _assert_trio()
        with pytest.raises(EventLoopBlockError) as exc_info:
            await bad_sleep_with_exception()

        assert len(exc_info.value.blocking_events) == 1
        blocking_event = exc_info.value.blocking_events[0]
        assert blocking_event.block_id == 1
        assert blocking_event.duration > 0.0
        assert blocking_event.timestamp > 0.0
        blocking_stack = blocking_event.format_blocking_stack()
        assert "bad_sleep_with_exception" in blocking_stack
        assert "time.sleep(1)" in blocking_stack


class TestTrioEventLoopBlockingContextManager:
    @pytest.mark.trio
    async def test_no_blocking(self):
        """Test that no warnings are issued when no event loop blocking is detected."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            async with no_event_loop_blocking(action="warn", threshold=0.5):
                await trio.sleep(1)

            assert len(w) == 0

    @pytest.mark.trio
    async def test_action_warning(self):
        """Test that event loop blocking triggers warnings."""
        _assert_trio()
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            async with no_event_loop_blocking(action="warn"):
                time.sleep(1)

            assert len(w) == 3
            assert issubclass(w[0].category, ResourceWarning)
            assert "Event loop blocked for" in str(w[0].message)
            assert "Detected 1 event loop blocks" in str(w[1].message)
            assert "time.sleep(1)" in str(w[2].message)

    @pytest.mark.trio
    async def test_action_raise(self):
        """Test that event loop blocking triggers exceptions."""
        _assert_trio()
        with pytest.raises(EventLoopBlockError) as exc_info:
            async with no_event_loop_blocking(action="raise"):
                time.sleep(1)

        assert len(exc_info.value.blocking_events) == 1
        blocking_event = exc_info.value.blocking_events[0]
        assert blocking_event.block_id == 1
        assert blocking_event.duration > 0.0
        assert blocking_event.timestamp > 0.0
        blocking_stack = blocking_event.format_blocking_stack()
        assert "time.sleep(1)" in blocking_stack
