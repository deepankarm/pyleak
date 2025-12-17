"""
PyLeak pytest plugin for detecting leaked tasks, threads, and event loop blocking.

This plugin automatically wraps tests with pyleak detectors based on pytest markers.
"""

from __future__ import annotations

import asyncio
import inspect
from unittest import TestCase

import pytest

from pyleak.combined import CombinedLeakDetector, PyLeakConfig
from pyleak.utils import CallerContext


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

    is_async = inspect.iscoroutinefunction(item.function)
    original_func = item.function
    caller_context = CallerContext(
        filename=item.fspath.strpath, name=item.name, lineno=None
    )

    # Check if this is a TestCase-based test
    instance = getattr(item, "instance", None)
    is_testcase = isinstance(instance, TestCase)

    if is_async:
        if is_testcase:
            # For TestCase methods, patch the method on the instance
            # because IsolatedAsyncioTestCase._callTestMethod retrieves
            # the method from self, not from item.obj
            original_method = getattr(instance, item.name)

            async def async_wrapper_testcase():
                detector = CombinedLeakDetector(
                    config=config, is_async=True, caller_context=caller_context
                )
                async with detector:
                    return await original_method()

            setattr(instance, item.name, async_wrapper_testcase)

            try:
                yield
            finally:
                setattr(instance, item.name, original_method)
        else:
            # For standalone async functions, replace item.obj as before
            async def async_wrapper(*args, **kwargs):
                detector = CombinedLeakDetector(
                    config=config, is_async=True, caller_context=caller_context
                )
                async with detector:
                    return await original_func(*args, **kwargs)

            item.obj = async_wrapper

            try:
                yield
            finally:
                item.obj = original_func
    else:

        def sync_wrapper(*args, **kwargs):
            detector = CombinedLeakDetector(
                config=config, is_async=False, caller_context=caller_context
            )
            with detector:
                return original_func(*args, **kwargs)

        item.obj = sync_wrapper

        try:
            yield
        finally:
            item.obj = original_func
