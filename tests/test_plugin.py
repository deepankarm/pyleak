import asyncio
import threading
import time

import pytest

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
