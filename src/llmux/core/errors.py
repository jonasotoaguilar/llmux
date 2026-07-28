"""LLMux error hierarchy and OpenAI-shaped envelope mapping.

Each :class:`LLMuxError` carries a deterministic HTTP ``status_code`` and
serializes to the OpenAI error envelope shape. Bodies never include
provider keys, upstream payloads, or stack traces.
"""

from __future__ import annotations

from typing import Any


class LLMuxError(Exception):
    """Base class for all LLMux errors that map to an HTTP response."""

    status_code: int = 500
    error_type: str = "internal_error"

    def __init__(self, message: str, **details: Any) -> None:
        super().__init__(message)
        self.message = message
        self.details = details

    def to_openai_envelope(self) -> dict[str, object]:
        return {
            "error": {
                "message": self.message,
                "type": self.error_type,
                "param": None,
                "code": self.error_type,
            }
        }


class ConfigurationError(LLMuxError):
    """Provider or gateway is mis-configured (status 502)."""

    status_code = 502
    error_type = "configuration_error"


class ProviderSelectionError(LLMuxError):
    """Requested model is not served by any enabled provider (status 400)."""

    status_code = 400
    error_type = "invalid_request_error"


class UpstreamError(LLMuxError):
    """Upstream provider returned a non-success status or transport error."""

    status_code = 502
    error_type = "upstream_error"


class UpstreamTimeoutError(LLMuxError):
    """Upstream provider call exceeded the configured timeout (status 504)."""

    status_code = 504
    error_type = "upstream_timeout_error"
