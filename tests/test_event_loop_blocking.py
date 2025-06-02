import asyncio
import time
import warnings

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from starlette.testclient import TestClient

from pyleak import EventLoopBlockError, no_event_loop_blocking

pytestmark = pytest.mark.asyncio


@no_event_loop_blocking(action="warn")
async def bad_sleep_with_warning():
    time.sleep(1)


@no_event_loop_blocking(action="raise")
async def bad_sleep_with_exception():
    time.sleep(1)


@no_event_loop_blocking(action="warn")
async def good_sleep_with_warning():
    await asyncio.sleep(1)


class TestEventLoopBlockingDecorator:
    async def test_no_event_loop_blocking(self):
        """Test that no warnings are issued when no event loop blocking is detected."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            await good_sleep_with_warning()
            assert len(w) == 0

    async def test_event_loop_blocking_with_warning(self):
        """Test that event loop blocking triggers warnings."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            await bad_sleep_with_warning()
            assert len(w) > 0
            assert issubclass(w[0].category, ResourceWarning)
            assert "Event loop blocked for" in str(w[0].message)

    async def test_event_loop_blocking_with_exception(self):
        """Test that event loop blocking triggers exceptions."""
        with pytest.raises(EventLoopBlockError) as exc_info:
            await bad_sleep_with_exception()

        assert "Event loop blocked for" in str(exc_info.value)


class TestEventLoopBlockingContextManager:
    async def test_good_sleep_with_warning(self):
        """Test that no warnings are issued when no event loop blocking is detected."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            async with no_event_loop_blocking(action="warn", threshold=0.5):
                await asyncio.sleep(1)

            assert len(w) == 0

    async def test_bad_sleep_with_warning(self):
        """Test that event loop blocking triggers warnings."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            async with no_event_loop_blocking(action="warn"):
                time.sleep(1)

            assert len(w) > 0
            assert issubclass(w[0].category, ResourceWarning)
            assert "Event loop blocked for" in str(w[0].message)

    async def test_bad_sleep_with_exception(self):
        """Test that event loop blocking triggers exceptions."""
        with pytest.raises(EventLoopBlockError) as exc_info:
            async with no_event_loop_blocking(action="raise"):
                time.sleep(1)

        assert "Event loop blocked for" in str(exc_info.value)


@pytest.fixture
def app():
    simple_fastapi_app = FastAPI()

    @simple_fastapi_app.get("/")
    async def endpoint(timeout: int = 0):
        await asyncio.sleep(timeout)
        return {"message": f"Hello World after {timeout} seconds"}

    return simple_fastapi_app


@pytest.fixture
def sync_client(app: FastAPI):
    return TestClient(app)


@pytest_asyncio.fixture
async def async_client(app: FastAPI):
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def my_function_using_sync_client(sync_client: TestClient):
    resp = sync_client.get("/", params={"timeout": 5})
    assert resp.status_code == 200
    assert resp.json() == {"message": "Hello World after 5 seconds"}


async def my_function_using_async_client(async_client: httpx.AsyncClient):
    resp = await async_client.get("/", params={"timeout": 5})
    assert resp.status_code == 200
    assert resp.json() == {"message": "Hello World after 5 seconds"}


class TestEventLoopBlockingWithHTTPRequests:
    async def test_event_loop_blocking_with_sync_client(
        self, sync_client, async_client
    ):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            async with no_event_loop_blocking(action="warn", threshold=0.2):
                await my_function_using_sync_client(sync_client)

            assert len(w) > 0
            assert issubclass(w[0].category, ResourceWarning)
            assert "Event loop blocked for" in str(w[0].message)

    async def test_event_loop_blocking_with_async_client(self, async_client):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            async with no_event_loop_blocking(action="warn", threshold=0.2):
                await my_function_using_async_client(async_client)

            assert len(w) == 0
