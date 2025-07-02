"""
Base classes for leak detection functionality.
"""

import logging
import re
import warnings
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, List, Optional, Set, Union

from exceptiongroup import ExceptionGroup

from pyleak.utils import setup_logger

_logger = setup_logger(__name__)


class LeakAction(str, Enum):
    """Actions to take when task leaks are detected."""

    WARN = "warn"
    LOG = "log"
    CANCEL = "cancel"
    RAISE = "raise"


class LeakError(Exception):
    """Base exception for leak detection errors."""


class PyleakExceptionGroup(ExceptionGroup, LeakError):
    """Combined exception for multiple leak errors."""

    def __init__(self, message: str, leak_errors: List[LeakError]):
        super().__init__(message, leak_errors)


class _BaseLeakDetector(ABC):
    """Base class for leak detection functionality."""

    def __init__(
        self,
        action: LeakAction = LeakAction.WARN,
        name_filter: Optional[Union[str, re.Pattern]] = None,
        logger: Optional[logging.Logger] = _logger,
    ):
        self.action = action
        self.name_filter = name_filter
        self.logger = logger

    def _matches_filter(self, resource_name: str) -> bool:
        """Check if resource name matches the filter."""
        if self.name_filter is None:
            return True

        if isinstance(self.name_filter, str):
            return resource_name == self.name_filter
        elif isinstance(self.name_filter, re.Pattern):
            return bool(self.name_filter.search(resource_name))
        else:
            # Try to compile as regex if it's a string-like pattern
            try:
                pattern = re.compile(str(self.name_filter))
                return bool(pattern.search(resource_name))
            except re.error:
                return resource_name == str(self.name_filter)

    @abstractmethod
    def _get_resource_name(self, resource: Any) -> str:
        """Get resource name, handling both named and unnamed resources."""
        pass

    @abstractmethod
    def get_running_resources(self, exclude_current: bool = True) -> Set[Any]:
        """Get all currently running resources."""
        pass

    @abstractmethod
    def _is_resource_active(self, resource: Any) -> bool:
        """Check if a resource is still active/running."""
        pass

    @property
    @abstractmethod
    def leak_error_class(self) -> type:
        """Get the appropriate exception class for this resource type."""
        pass

    @property
    @abstractmethod
    def resource_type(self) -> str:
        """Get the human-readable name for this resource type (e.g., 'tasks', 'threads')."""
        pass

    @abstractmethod
    def _handle_cancel_action(
        self, leaked_resources: List[Any], resource_names: List[str]
    ) -> None:
        """Handle the cancel action for leaked resources."""
        pass

    def get_leaked_resources(self, initial_resources: Set[Any]) -> List[Any]:
        """Find resources that are still running and match the filter."""
        current_resources = self.get_running_resources()
        new_resources = current_resources - initial_resources
        self.logger.debug(
            f"Found {len(new_resources)} new {self.resource_type} before filtering"
        )

        leaked_resources = []
        for resource in new_resources:
            if self._is_resource_active(resource):
                resource_name = self._get_resource_name(resource)
                if self._matches_filter(resource_name):
                    leaked_resources.append(resource)

        return leaked_resources

    def handle_leaked_resources(self, leaked_resources: List[Any]) -> None:
        """Handle detected leaked resources based on the configured action."""
        if not leaked_resources:
            return

        resource_names = [self._get_resource_name(r) for r in leaked_resources]
        message = f"Detected {len(leaked_resources)} leaked {self.resource_type}: {resource_names}"
        if self.action == "warn":
            warnings.warn(message, ResourceWarning, stacklevel=3)
        elif self.action == "log":
            self.logger.warning(message)
        elif self.action == "cancel":
            self._handle_cancel_action(leaked_resources, resource_names)
        elif self.action == "raise":
            raise self.leak_error_class(message)


class _BaseLeakContextManager(ABC):
    """Base context manager that can also be used as a decorator."""

    def __init__(
        self,
        action: str = "warn",
        name_filter: Optional[Union[str, re.Pattern]] = None,
        logger: Optional[logging.Logger] = _logger,
        **kwargs,
    ):
        self.action = action
        self.name_filter = name_filter
        self.logger = logger
        self.extra_kwargs = kwargs

    @abstractmethod
    def _create_detector(self) -> _BaseLeakDetector:
        """Create the appropriate detector instance."""
        pass

    @abstractmethod
    def _wait_for_completion(self) -> None:
        """Wait for resources to complete naturally."""
        pass

    def __enter__(self):
        return self._enter_context()

    def __exit__(self, exc_type, exc_val, exc_tb):
        return self._exit_context(exc_type, exc_val, exc_tb)

    def _enter_context(self):
        """Common enter logic."""
        self.detector = self._create_detector()
        self.initial_resources = self.detector.get_running_resources()
        self.logger.debug(
            f"Detected {len(self.initial_resources)} initial {self.detector.resource_type}"
        )
        return self

    def _exit_context(self, exc_type, exc_val, exc_tb):
        """Common exit logic."""
        self._wait_for_completion()
        leaked_resources = self.detector.get_leaked_resources(self.initial_resources)
        self.logger.debug(
            f"Detected {len(leaked_resources)} leaked {self.detector.resource_type}"
        )
        self.detector.handle_leaked_resources(leaked_resources)

    async def __aenter__(self):
        return self._enter_context()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return self._exit_context(exc_type, exc_val, exc_tb)
