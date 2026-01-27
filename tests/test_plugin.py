import asyncio
import threading
import time

import pytest
import sniffio
import trio

from exceptiongroup import BaseExceptionGroup

from pyleak import PyleakExceptionGroup


@pytest.mark.no_leaks
def test_sync_no_leaks():
    """Test sync function with no leaks"""
    pass


@pytest.mark.no_leaks
@pytest.mark.asyncio
async def test_async_no_leaks():
    """Test async function with no leaks"""
    await asyncio.sleep(0.01)


@pytest.mark.no_leaks("threads")
def test_sync_thread_only():
    """Test sync with thread detection only"""
    pass


@pytest.mark.xfail(raises=PyleakExceptionGroup)
@pytest.mark.no_leaks
@pytest.mark.asyncio
async def test_task_leak_detected():
    """This test should fail due to task leak"""
    asyncio.create_task(asyncio.sleep(10))  # Intentional leak


@pytest.mark.xfail(raises=PyleakExceptionGroup)
@pytest.mark.no_leaks
@pytest.mark.asyncio
async def test_thread_leak_detected():
    """This test should fail due to thread leak"""
    threading.Thread(target=lambda: time.sleep(10)).start()  # Intentional leak


@pytest.mark.xfail(raises=PyleakExceptionGroup)
@pytest.mark.no_leaks
@pytest.mark.asyncio
async def test_blocking_detected():
    """This test should fail due to blocking"""
    time.sleep(0.5)  # Intentional blocking


@pytest.mark.xfail(raises=PyleakExceptionGroup)
@pytest.mark.no_leaks
def test_sync_thread_leak_detected():
    """This test should fail due to thread leak"""
    threading.Thread(target=lambda: time.sleep(10)).start()  # Intentional leak


@pytest.mark.no_leaks(tasks=True, threads=False, blocking=False)
@pytest.mark.asyncio
async def test_task_leak_detected_no_blocking():
    """This test should pass as we only capture tasks"""
    await asyncio.create_task(asyncio.sleep(0.1))  # no tasks leak
    time.sleep(0.5)  # intentionally block the event loop


# Regression tests for issue #14: CombinedLeakDetector false positives


@pytest.mark.no_leaks(tasks=True, threads=False, blocking=True)
@pytest.mark.asyncio
async def test_no_false_positive_ping_event_loop_task():
    """Task detector should not detect blocking detector's internal _ping_event_loop task."""
    await asyncio.sleep(0.01)


@pytest.mark.no_leaks(tasks=False, threads=True, blocking=True, blocking_threshold=0.05)
@pytest.mark.asyncio
async def test_no_false_positive_thread_grace_period_block():
    """Blocking detector should not detect thread detector's grace_period sleep."""
    await asyncio.sleep(0.01)


@pytest.mark.no_leaks(tasks=True, threads=True, blocking=True, blocking_threshold=0.05)
@pytest.mark.asyncio
async def test_combined_detector_no_false_positives():
    """All detectors enabled should not cause false positives from interactions."""
    await asyncio.sleep(0.01)


# Trio plugin tests


@pytest.mark.no_leaks(tasks=False, threads=False, blocking=False)
@pytest.mark.trio
async def test_trio_no_leaks():
    """Test trio function with no leaks and all detectors disabled."""
    assert sniffio.current_async_library() == "trio"
    await trio.sleep(0.01)


@pytest.mark.no_leaks(tasks=False, threads=True, blocking=True)
@pytest.mark.trio
async def test_trio_no_leaks_threads_and_blocking():
    """Test trio function with thread and blocking detection enabled, no issues."""
    assert sniffio.current_async_library() == "trio"
    await trio.sleep(0.01)


@pytest.mark.xfail(raises=(PyleakExceptionGroup, BaseExceptionGroup))
@pytest.mark.no_leaks(tasks=False, threads=True, blocking=False)
@pytest.mark.trio
async def test_trio_thread_leak_detected():
    """This test should fail due to thread leak under trio."""
    assert sniffio.current_async_library() == "trio"
    threading.Thread(target=lambda: time.sleep(10)).start()


@pytest.mark.xfail(raises=(PyleakExceptionGroup, BaseExceptionGroup))
@pytest.mark.no_leaks(tasks=False, threads=False, blocking=True)
@pytest.mark.trio
async def test_trio_blocking_detected():
    """This test should fail due to blocking under trio."""
    assert sniffio.current_async_library() == "trio"
    time.sleep(0.5)
