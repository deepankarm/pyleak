"""
PyLeak pytest plugin for detecting leaked tasks, threads, and event loop blocking.

This plugin automatically wraps tests with pyleak detectors based on pytest markers.
"""

from __future__ import annotations

import asyncio

import pytest

from pyleak.combined import CombinedLeakDetector, PyLeakConfig


def should_monitor_test(item: pytest.Function) -> PyLeakConfig | None:
    """Check if test should be monitored and return config"""
    marker = item.get_closest_marker("no_leaks")
    if not marker:
        return None

    marker_args = {}
    if marker.args:
        for arg in marker.args:
            if arg == "tasks":
                marker_args["tasks"] = True
            elif arg == "threads":
                marker_args["threads"] = True
            elif arg == "blocking":
                marker_args["blocking"] = True
            elif arg == "all":
                marker_args.update({"tasks": True, "threads": True, "blocking": True})

    if marker.kwargs:
        marker_args.update(marker.kwargs)

    if not marker_args:
        marker_args = {"tasks": True, "threads": True, "blocking": True}

    return PyLeakConfig.from_marker_args(marker_args)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item: pytest.Function):
    """Wrap test execution with leak detection"""

    config = should_monitor_test(item)
    if not config:
        yield
        return

    is_async = asyncio.iscoroutinefunction(item.function)
    original_func = item.function

    if is_async:

        async def async_wrapper(*args, **kwargs):
            detector = CombinedLeakDetector(config, is_async=True)
            async with detector:
                return await original_func(*args, **kwargs)

        item.obj = async_wrapper
    else:

        def sync_wrapper(*args, **kwargs):
            detector = CombinedLeakDetector(config, is_async=False)
            with detector:
                return original_func(*args, **kwargs)

        item.obj = sync_wrapper

    try:
        yield
    finally:
        item.obj = original_func
