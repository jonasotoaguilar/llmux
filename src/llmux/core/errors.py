"""LLMux error hierarchy and OpenAI-shaped error envelope mapping.

Each :class:`LLMuxError` carries a deterministic HTTP ``status_code`` and
serializes to the OpenAI error envelope shape. Envelopes never include API
keys, upstream payloads, or stack traces — sensitive data passed to the
exception constructor is ignored by :func:`to_openai_envelope`.

    Status / code map (per ``design.md``):
    ===========================  ====  =============================
    Error class                   HTTP  Stable code
    ===========================  ====  =============================
    ``ProviderSelectionError``     400  ``model_not_found``
    ``ConfigurationError``         502  ``provider_configuration_error``
    ``UpstreamError``              502  ``upstream_error``
    ``UpstreamTimeoutError``       504  ``upstream_timeout``
    ``AllProvidersFailedError``    503  ``all_providers_failed``
    ===========================  ====  =============================
"""

from __future__ import annotations

from typing import Any


class LLMuxError(Exception):
    """Base class for every LLMux error that maps to an HTTP response."""

    status_code: int = 500
    code: str = "internal_error"
    error_type: str = "api_error"
    safe_message: str = "An internal error occurred"

    def __init__(self, message: str = "", **details: Any) -> None:
        super().__init__(message)
        self._raw_message = message
        self.details = details

    def to_openai_envelope(self) -> dict[str, Any]:
        """Return an OpenAI-shaped error body. Safe for HTTP responses.

        The raw constructor message is intentionally discarded; only the
        class-level ``safe_message`` reaches the wire.
        """
        return {
            "error": {
                "message": type(self).safe_message,
                "type": type(self).error_type,
                "param": None,
                "code": type(self).code,
            }
        }


class ConfigurationError(LLMuxError):
    """Provider or gateway is mis-configured (HTTP 502 if surfaced)."""

    status_code = 502
    code = "provider_configuration_error"
    safe_message = "Provider configuration error"


class ProviderSelectionError(LLMuxError):
    """Requested model is not served by any enabled provider (HTTP 400)."""

    status_code = 400
    code = "model_not_found"
    error_type = "invalid_request_error"
    safe_message = "Requested model is not available"


class UpstreamError(LLMuxError):
    """Upstream provider returned a non-success status or transport error."""

    status_code = 502
    code = "upstream_error"
    safe_message = "Upstream provider error"


class UpstreamTimeoutError(UpstreamError):
    """Upstream provider call exceeded the configured timeout (HTTP 504)."""

    status_code = 504
    code = "upstream_timeout"
    safe_message = "Upstream provider request timed out"


class AllProvidersFailedError(LLMuxError):
    """Every candidate provider failed retryably (HTTP 503 if surfaced).

    Raised by the attempt chain when all candidates are exhausted; the
    OpenAI-shaped envelope carries the stable ``all_providers_failed``
    code and the class-level safe message, never upstream bodies, keys,
    or stack traces. It is the terminal exhaustion signal of the
    attempt chain and is never itself retryable (:func:`is_retryable`
    returns ``False``).
    """

    status_code = 503
    code = "all_providers_failed"
    safe_message = "All providers failed"


def is_retryable(error: LLMuxError) -> bool:
    """Return whether ``error`` permits a fallback attempt.

    Timeout errors are always retryable. Upstream errors are retryable
    when the upstream reported 408, 429, or a 5xx status, and when no
    status is known (transport failure). Every other status — the
    remaining 4xx ``UpstreamError`` cases — and every non-upstream
    typed error (selection, configuration, internal) is terminal.
    """
    if isinstance(error, UpstreamTimeoutError):
        return True
    if isinstance(error, UpstreamError):
        status = error.details.get("status")
        if status is None:
            return True
        return status in (408, 429) or status >= 500
    return False


def to_openai_envelope(error: LLMuxError) -> dict[str, Any]:
    """Return the OpenAI-shaped error body for any :class:`LLMuxError`."""
    return error.to_openai_envelope()
