"""
Event Core Exceptions.

Custom exceptions for the Event Engine and related components.
All exceptions follow a consistent pattern for easy error handling.

Author: Tactical Core Engineering Team
Version: 1.0
"""

from typing import Any, Optional


class EventCoreException(Exception):
    """
    Base exception for Event Core components.

    All Event Engine exceptions inherit from this class.
    Provides consistent error handling across the system.

    Attributes:
        message: Human-readable error message.
        code: Error code for programmatic handling.
        details: Additional error details.
        original_error: The exception that caused this error.
    """

    def __init__(
        self,
        message: str,
        code: str = "EVENT_CORE_ERROR",
        details: Optional[dict] = None,
        original_error: Optional[Exception] = None,
    ) -> None:
        """
        Initialize the exception.

        Args:
            message: Human-readable error message.
            code: Error code for programmatic handling.
            details: Additional error context.
            original_error: Original exception if any.
        """
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}
        self.original_error = original_error

    def __str__(self) -> str:
        """Return string representation of the exception."""
        return f"[{self.code}] {self.message}"

    def to_dict(self) -> dict:
        """Convert exception to dictionary for API responses."""
        return {
            "error": self.code,
            "message": self.message,
            "details": self.details,
        }


class EventValidationError(EventCoreException):
    """
    Exception raised when event validation fails.

    Raised when an event fails schema validation or
    business rule validation.

    Attributes:
        field: The field that failed validation.
        value: The invalid value.
        constraint: The constraint that was violated.
    """

    def __init__(
        self,
        message: str,
        field: Optional[str] = None,
        value: Any = None,
        constraint: Optional[str] = None,
        details: Optional[dict] = None,
    ) -> None:
        """
        Initialize the validation error.

        Args:
            message: Human-readable error message.
            field: Name of the field that failed validation.
            value: The invalid value.
            constraint: Description of the violated constraint.
            details: Additional error context.
        """
        extra_details = {
            "field": field,
            "value": str(value) if value is not None else None,
            "constraint": constraint,
        }
        if details:
            extra_details.update(details)

        super().__init__(
            message=message,
            code="EVENT_VALIDATION_ERROR",
            details=extra_details,
        )
        self.field = field
        self.value = value
        self.constraint = constraint


class EventPersistenceError(EventCoreException):
    """
    Exception raised when event persistence fails.

    Raised when the Event Engine cannot save an event
    to the database or storage.

    Attributes:
        event_id: The ID of the event that failed to persist.
        storage_type: The type of storage (database, file, etc.).
    """

    def __init__(
        self,
        message: str,
        event_id: Optional[str] = None,
        storage_type: str = "database",
        details: Optional[dict] = None,
        original_error: Optional[Exception] = None,
    ) -> None:
        """
        Initialize the persistence error.

        Args:
            message: Human-readable error message.
            event_id: ID of the event that failed to persist.
            storage_type: Type of storage (database, file, etc.).
            details: Additional error context.
            original_error: Original database/IO exception.
        """
        extra_details = {
            "event_id": event_id,
            "storage_type": storage_type,
        }
        if details:
            extra_details.update(details)

        super().__init__(
            message=message,
            code="EVENT_PERSISTENCE_ERROR",
            details=extra_details,
            original_error=original_error,
        )
        self.event_id = event_id
        self.storage_type = storage_type


class EventDispatchError(EventCoreException):
    """
    Exception raised when event dispatch fails.

    Raised when the Event Engine cannot dispatch an event
    to one or more subscribers.

    Attributes:
        event_id: The ID of the event that failed to dispatch.
        subscriber: The subscriber that failed.
        error_type: Type of dispatch error.
    """

    def __init__(
        self,
        message: str,
        event_id: Optional[str] = None,
        subscriber: Optional[str] = None,
        error_type: str = "unknown",
        details: Optional[dict] = None,
        original_error: Optional[Exception] = None,
    ) -> None:
        """
        Initialize the dispatch error.

        Args:
            message: Human-readable error message.
            event_id: ID of the event that failed to dispatch.
            subscriber: Name/ID of the subscriber.
            error_type: Type of dispatch error.
            details: Additional error context.
            original_error: Original exception from subscriber.
        """
        extra_details = {
            "event_id": event_id,
            "subscriber": subscriber,
            "error_type": error_type,
        }
        if details:
            extra_details.update(details)

        super().__init__(
            message=message,
            code="EVENT_DISPATCH_ERROR",
            details=extra_details,
            original_error=original_error,
        )
        self.event_id = event_id
        self.subscriber = subscriber
        self.error_type = error_type


class PluginRegistrationError(EventCoreException):
    """
    Exception raised when plugin registration fails.

    Raised when a plugin cannot be registered with the
    Event Engine due to validation or compatibility issues.

    Attributes:
        plugin_id: The ID of the plugin that failed to register.
        reason: Reason for the failure.
    """

    def __init__(
        self,
        message: str,
        plugin_id: Optional[str] = None,
        reason: str = "unknown",
        details: Optional[dict] = None,
        original_error: Optional[Exception] = None,
    ) -> None:
        """
        Initialize the plugin registration error.

        Args:
            message: Human-readable error message.
            plugin_id: ID of the plugin.
            reason: Reason for registration failure.
            details: Additional error context.
            original_error: Original exception.
        """
        extra_details = {
            "plugin_id": plugin_id,
            "reason": reason,
        }
        if details:
            extra_details.update(details)

        super().__init__(
            message=message,
            code="PLUGIN_REGISTRATION_ERROR",
            details=extra_details,
            original_error=original_error,
        )
        self.plugin_id = plugin_id
        self.reason = reason


class SubscriberError(EventCoreException):
    """
    Exception raised when a subscriber handler fails.

    Raised when a subscriber's event handler raises an exception.
    The Event Engine catches this and continues processing.

    Attributes:
        subscriber_id: The ID of the subscriber.
        event_id: The ID of the event being processed.
        handler_name: Name of the handler that failed.
    """

    def __init__(
        self,
        message: str,
        subscriber_id: Optional[str] = None,
        event_id: Optional[str] = None,
        handler_name: Optional[str] = None,
        details: Optional[dict] = None,
        original_error: Optional[Exception] = None,
    ) -> None:
        """
        Initialize the subscriber error.

        Args:
            message: Human-readable error message.
            subscriber_id: ID of the subscriber.
            event_id: ID of the event being processed.
            handler_name: Name of the handler that failed.
            details: Additional error context.
            original_error: Original exception from handler.
        """
        extra_details = {
            "subscriber_id": subscriber_id,
            "event_id": event_id,
            "handler_name": handler_name,
        }
        if details:
            extra_details.update(details)

        super().__init__(
            message=message,
            code="SUBSCRIBER_ERROR",
            details=extra_details,
            original_error=original_error,
        )
        self.subscriber_id = subscriber_id
        self.event_id = event_id
        self.handler_name = handler_name


class EventBusError(EventCoreException):
    """
    Exception raised for Event Bus operation failures.

    Raised when the Event Bus cannot complete an operation
    such as subscribe, unsubscribe, or publish.

    Attributes:
        operation: The operation that failed.
        queue_name: Name of the affected queue if any.
    """

    def __init__(
        self,
        message: str,
        operation: str = "unknown",
        queue_name: Optional[str] = None,
        details: Optional[dict] = None,
        original_error: Optional[Exception] = None,
    ) -> None:
        """
        Initialize the Event Bus error.

        Args:
            message: Human-readable error message.
            operation: The operation that failed.
            queue_name: Name of the affected queue.
            details: Additional error context.
            original_error: Original exception.
        """
        extra_details = {
            "operation": operation,
            "queue_name": queue_name,
        }
        if details:
            extra_details.update(details)

        super().__init__(
            message=message,
            code="EVENT_BUS_ERROR",
            details=extra_details,
            original_error=original_error,
        )
        self.operation = operation
        self.queue_name = queue_name


class EventHistoryError(EventCoreException):
    """
    Exception raised for Event History operation failures.

    Raised when the Event History cannot complete an operation
    such as storing, searching, or replaying events.
    """

    def __init__(
        self,
        message: str,
        operation: str = "unknown",
        event_id: Optional[str] = None,
        details: Optional[dict] = None,
        original_error: Optional[Exception] = None,
    ) -> None:
        """
        Initialize the Event History error.

        Args:
            message: Human-readable error message.
            operation: The operation that failed.
            event_id: ID of the event if applicable.
            details: Additional error context.
            original_error: Original exception.
        """
        extra_details = {
            "operation": operation,
            "event_id": event_id,
        }
        if details:
            extra_details.update(details)

        super().__init__(
            message=message,
            code="EVENT_HISTORY_ERROR",
            details=extra_details,
            original_error=original_error,
        )
        self.operation = operation
        self.event_id = event_id
