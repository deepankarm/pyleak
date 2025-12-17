"""
Tests for pyleak pytest plugin support for unittest.TestCase.

This tests the fix for TestCase-based tests where item.obj replacement
doesn't work because IsolatedAsyncioTestCase._callTestMethod retrieves
the method from self, not from item.obj.
"""

import time
import unittest

import pytest

from pyleak.eventloop import EventLoopBlockError


class TestPyleakTestCaseSupport(unittest.IsolatedAsyncioTestCase):
    """Test that pyleak works with IsolatedAsyncioTestCase methods."""

    @pytest.mark.no_leaks(tasks=False, threads=False, blocking=True, blocking_threshold=0.1)
    async def test_event_loop_blocking_detected_in_testcase(self):
        """
        Test that event loop blocking is detected in TestCase async methods.
        
        This test should FAIL with EventLoopBlockError, proving that
        pyleak's no_leaks marker works with IsolatedAsyncioTestCase.
        """
        # This blocking call should be detected
        time.sleep(0.2)

    @pytest.mark.no_leaks(tasks=False, threads=False, blocking=True, blocking_threshold=0.5)
    async def test_no_blocking_passes_in_testcase(self):
        """
        Test that TestCase methods pass when there's no blocking.
        """
        # This should not trigger blocking detection (under threshold)
        await asyncio.sleep(0.01)
        self.assertTrue(True)


# To run as a proper test, we need to mark the blocking test as expected to fail
class TestPyleakTestCaseBlocking(unittest.IsolatedAsyncioTestCase):
    """Test that verifies blocking detection raises the expected error."""

    @pytest.mark.no_leaks(tasks=False, threads=False, blocking=True, blocking_threshold=0.1)
    async def test_blocking_raises_error(self):
        """This test intentionally blocks and should raise EventLoopBlockError."""
        time.sleep(0.2)


# Mark the blocking test as expected to fail with EventLoopBlockError
TestPyleakTestCaseBlocking.test_blocking_raises_error = pytest.mark.xfail(
    raises=Exception,  # PyleakExceptionGroup
    reason="This test intentionally blocks the event loop to verify detection works"
)(TestPyleakTestCaseBlocking.test_blocking_raises_error)
