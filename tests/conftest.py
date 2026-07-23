"""Shared test harness: FastAPI TestClient fixture and ASGI helpers."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from llmux.config import Settings
from llmux.main import create_app


@pytest.fixture
def app() -> FastAPI:
    settings = Settings.model_construct(
        llmux_host="127.0.0.1",
        llmux_port=8000,
        llmux_version="0.1.0",
        llmux_providers_configured=[],
        otel_service_name="llmux-test",
        otel_exporter_otlp_endpoint="",
    )
    return create_app(settings=settings)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client
