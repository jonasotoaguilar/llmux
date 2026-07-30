"""Provider routing functional slice — PR1 (config + errors)."""

from __future__ import annotations

import json
from urllib.parse import quote

import pytest
from pydantic import SecretStr

from llmux.config import Settings
from llmux.core.errors import (
    ConfigurationError,
    LLMuxError,
    ProviderSelectionError,
    UpstreamError,
    UpstreamTimeoutError,
    to_openai_envelope,
)

_OPENAI_ENV = (
    "LLMUX_PROVIDERS_CONFIGURED",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "OPENAI_MODELS",
    "OPENAI_TIMEOUT_S",
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in _OPENAI_ENV:
        monkeypatch.delenv(var, raising=False)


def _enable(
    monkeypatch: pytest.MonkeyPatch,
    *,
    api_key: str | None = "sk-test",
    base_url: str = "https://api.openai.com/v1",
    models: str = "gpt-4o-mini",
) -> None:
    monkeypatch.setenv("LLMUX_PROVIDERS_CONFIGURED", "openai")
    if api_key is not None:
        monkeypatch.setenv("OPENAI_API_KEY", api_key)
    monkeypatch.setenv("OPENAI_BASE_URL", base_url)
    monkeypatch.setenv("OPENAI_MODELS", models)


# ----- 1.1 / 1.2 — OpenAI settings (valid + fail-fast ConfigurationError) --


def test_openai_settings_valid_parses_all_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable(monkeypatch, api_key="sk-abc", models='["gpt-4o-mini","gpt-4o"]')
    monkeypatch.setenv("OPENAI_TIMEOUT_S", "12.5")
    s = Settings()  # type: ignore[call-arg]
    assert isinstance(s.openai_api_key, SecretStr)
    assert s.openai_api_key.get_secret_value() == "sk-abc"
    assert s.openai_base_url == "https://api.openai.com/v1"
    assert s.openai_models == ["gpt-4o-mini", "gpt-4o"]
    assert s.openai_timeout_s == 12.5


def test_openai_settings_default_when_no_provider_configured() -> None:
    s = Settings()  # type: ignore[call-arg]
    assert s.llmux_providers_configured == []
    assert s.openai_api_key is None
    assert s.openai_models == []
    assert s.openai_base_url == "https://api.openai.com/v1"
    assert s.openai_timeout_s == 30.0


@pytest.mark.parametrize(
    "api_key,base_url,models,expected",
    [
        ("", "https://api.openai.com/v1", "gpt-4o-mini", "OPENAI_API_KEY"),
        ("sk-abc", "https://api.openai.com/v1", "", "OPENAI_MODELS"),
        ("sk-abc", "not-a-url", "gpt-4o-mini", "OPENAI_BASE_URL"),
    ],
    ids=["empty_key", "empty_models", "invalid_url"],
)
def test_openai_settings_invalid_raises_configuration_error(
    monkeypatch: pytest.MonkeyPatch,
    api_key: str,
    base_url: str,
    models: str,
    expected: str,
) -> None:
    _enable(monkeypatch, api_key=api_key, base_url=base_url, models=models)
    with pytest.raises(ConfigurationError) as exc:
        Settings()  # type: ignore[call-arg]
    assert expected in str(exc.value)


# ----- 1.3 / 1.4 — LLMuxError hierarchy + to_openai_envelope ----------------


@pytest.mark.parametrize(
    "cls,status,code,type_",
    [
        (ProviderSelectionError, 400, "model_not_found", "invalid_request_error"),
        (ConfigurationError, 502, "provider_configuration_error", "api_error"),
        (UpstreamError, 502, "upstream_error", "api_error"),
        (UpstreamTimeoutError, 504, "upstream_timeout", "api_error"),
    ],
    ids=["selection", "config", "upstream", "timeout"],
)
def test_errors_envelope_status_and_codes(
    cls: type[LLMuxError], status: int, code: str, type_: str
) -> None:
    err = cls("sensitive-secret-1234")
    body = to_openai_envelope(err)
    assert err.status_code == status
    assert body["error"]["code"] == code
    assert body["error"]["type"] == type_
    assert body["error"]["param"] is None
    # Class-level safe message — never the raw constructor arg.
    assert "sensitive-secret-1234" not in body["error"]["message"]


def test_errors_envelope_timeout_is_upstream_subclass() -> None:
    """UpstreamTimeoutError subclasses UpstreamError so a single
    ``except UpstreamError`` catches the timeout path; status is 504."""
    err = UpstreamTimeoutError("timeout")
    assert isinstance(err, UpstreamError)
    assert err.status_code == 504
    assert to_openai_envelope(err)["error"]["code"] == "upstream_timeout"


def test_errors_envelope_sanitized() -> None:
    """Envelopes never include raw exception text, keys, upstream payloads,
    or stack traces — only the class-level safe fields, in a fixed shape."""
    secret = (
        f"key sk-{quote('AKIA-EXAMPLE')}, body=<html>no</html>, "
        "Traceback (most recent call last):\n  File 'x.py', line 1"
    )
    sensitive = ("AKIA-EXAMPLE", "sk-EXAMPLE", "<html>", "Traceback", "File 'x.py'")
    for cls in (
        ConfigurationError,
        ProviderSelectionError,
        UpstreamError,
        UpstreamTimeoutError,
    ):
        body = to_openai_envelope(cls(secret))
        serialized = json.dumps(body)
        for token in sensitive:
            assert token not in serialized, f"{cls.__name__} leaked {token!r}"
        # Stable, OpenAI-shaped envelope: exactly one ``error`` key.
        assert set(body.keys()) == {"error"}
        assert set(body["error"].keys()) == {"message", "type", "param", "code"}


def test_errors_envelope_unknown_subclass_uses_base_defaults() -> None:
    """An ad-hoc LLMuxError subclass without overrides falls back to the
    base defaults so the envelope is well-formed and the status set."""

    class Custom(LLMuxError):  # noqa: N818
        pass

    body = to_openai_envelope(Custom("should-not-leak"))
    assert Custom().status_code == 500
    assert body["error"]["code"] == "internal_error"
    assert "should-not-leak" not in json.dumps(body)
