from __future__ import annotations

import pytest

from company_agent.providers import _PROXY_HANDLER, ProviderError, client_by_provider

PLATFORM = client_by_provider("uniqon")


def test_provider_client_disables_environment_proxies() -> None:
    assert _PROXY_HANDLER.proxies == {}


def test_malformed_provider_contract_fails_closed(monkeypatch) -> None:
    monkeypatch.setattr("company_agent.providers.load_providers", lambda: {"providers": [{}]})
    with pytest.raises(ProviderError, match="provider contract is invalid"):
        client_by_provider("uniqon")


def test_provider_rejects_invalid_token_characters(monkeypatch) -> None:
    monkeypatch.setenv("COMPANY_QUANTUM_PLATFORM_INVOKE_URL", "http://127.0.0.1:1/invoke")
    monkeypatch.setenv("COMPANY_QUANTUM_PLATFORM_TOKEN", "good\r\nInjected: bad")
    client = client_by_provider("uniqon")
    with pytest.raises(ProviderError, match="contains invalid characters"):
        client.invoke(
            "algorithm.run",
            {"catalog_version": "cat_fixture", "component_version": "1.0", "algorithm": "vqe"},
        )


def test_provider_requires_declared_token(monkeypatch) -> None:
    monkeypatch.setenv("COMPANY_QUANTUM_PLATFORM_INVOKE_URL", "http://127.0.0.1:1/invoke")
    monkeypatch.delenv("COMPANY_QUANTUM_PLATFORM_TOKEN", raising=False)
    client = client_by_provider("uniqon")
    assert client.configured() is False
    with pytest.raises(ProviderError, match="COMPANY_QUANTUM_PLATFORM_TOKEN is not configured"):
        client.invoke(
            "algorithm.run",
            {"catalog_version": "cat_fixture", "component_version": "1.0", "algorithm": "vqe"},
        )


def test_provider_rejects_operation_outside_contract(monkeypatch) -> None:
    monkeypatch.setenv("COMPANY_QUANTUM_PLATFORM_INVOKE_URL", "http://127.0.0.1:1/invoke")
    try:
        PLATFORM.invoke("device.run", {})
    except ProviderError as exc:
        assert "not allowed" in str(exc)
    else:
        raise AssertionError("operation outside provider contract was accepted")


def test_provider_rejects_non_http_endpoint(monkeypatch) -> None:
    monkeypatch.setenv("COMPANY_QUANTUM_PLATFORM_INVOKE_URL", "file:///tmp/provider.json")
    client = client_by_provider("uniqon")
    assert client.configured() is False
    with pytest.raises(ProviderError, match="absolute HTTP"):
        client.invoke(
            "algorithm.run",
            {"catalog_version": "cat_fixture", "component_version": "1.0", "algorithm": "vqe"},
        )


def test_provider_rejects_embedded_credentials(monkeypatch) -> None:
    monkeypatch.setenv(
        "COMPANY_QUANTUM_PLATFORM_INVOKE_URL",
        "https://user:password@example.invalid/invoke",
    )
    client = client_by_provider("uniqon")
    assert client.configured() is False
    with pytest.raises(ProviderError, match="forbidden URL components"):
        client.invoke(
            "algorithm.run",
            {"catalog_version": "cat_fixture", "component_version": "1.0", "algorithm": "vqe"},
        )


def test_provider_rejects_query_string(monkeypatch) -> None:
    monkeypatch.setenv(
        "COMPANY_QUANTUM_PLATFORM_INVOKE_URL",
        "https://example.invalid/invoke?token=leaked",
    )
    client = client_by_provider("uniqon")
    assert client.configured() is False
    with pytest.raises(ProviderError, match="must not contain a query string"):
        client.invoke(
            "algorithm.run",
            {"catalog_version": "cat_fixture", "component_version": "1.0", "algorithm": "vqe"},
        )


def test_provider_accepts_case_insensitive_loopback_hostname(monkeypatch) -> None:
    monkeypatch.setenv("COMPANY_QUANTUM_PLATFORM_INVOKE_URL", "http://localhost:1/invoke")
    client = client_by_provider("uniqon")
    assert client.endpoint() == "http://localhost:1/invoke"


def test_provider_accepts_numeric_loopback_range(monkeypatch) -> None:
    monkeypatch.setenv("COMPANY_QUANTUM_PLATFORM_INVOKE_URL", "http://127.0.0.2:1/invoke")
    client = client_by_provider("uniqon")
    assert client.endpoint() == "http://127.0.0.2:1/invoke"


def test_provider_rejects_encoded_control_character(monkeypatch) -> None:
    monkeypatch.setenv(
        "COMPANY_QUANTUM_PLATFORM_INVOKE_URL",
        "https://example.invalid/api/%0d%0aInjected",
    )
    client = client_by_provider("uniqon")
    assert client.configured() is False
    with pytest.raises(ProviderError, match="invalid path characters"):
        client.invoke(
            "algorithm.run",
            {"catalog_version": "cat_fixture", "component_version": "1.0", "algorithm": "vqe"},
        )


def test_provider_rejects_encoded_path_traversal(monkeypatch) -> None:
    monkeypatch.setenv(
        "COMPANY_QUANTUM_PLATFORM_INVOKE_URL",
        "https://example.invalid/api/%2e%2e/private",
    )
    client = client_by_provider("uniqon")
    assert client.configured() is False
    with pytest.raises(ProviderError, match="forbidden path traversal"):
        client.invoke(
            "algorithm.run",
            {"catalog_version": "cat_fixture", "component_version": "1.0", "algorithm": "vqe"},
        )


def test_provider_requires_explicit_invoke_path(monkeypatch) -> None:
    monkeypatch.setenv("COMPANY_QUANTUM_PLATFORM_INVOKE_URL", "https://example.invalid/")
    client = client_by_provider("uniqon")
    assert client.configured() is False
    with pytest.raises(ProviderError, match="explicit invoke path"):
        client.invoke(
            "algorithm.run",
            {"catalog_version": "cat_fixture", "component_version": "1.0", "algorithm": "vqe"},
        )


def test_provider_rejects_unicode_hostname(monkeypatch) -> None:
    monkeypatch.setenv("COMPANY_QUANTUM_PLATFORM_INVOKE_URL", "https://例子.测试/invoke")
    client = client_by_provider("uniqon")
    assert client.configured() is False
    with pytest.raises(ProviderError, match="ASCII or punycode"):
        client.invoke(
            "algorithm.run",
            {"catalog_version": "cat_fixture", "component_version": "1.0", "algorithm": "vqe"},
        )


def test_provider_rejects_invalid_port(monkeypatch) -> None:
    monkeypatch.setenv("COMPANY_QUANTUM_PLATFORM_INVOKE_URL", "http://127.0.0.1:99999/invoke")
    client = client_by_provider("uniqon")
    assert client.configured() is False
    with pytest.raises(ProviderError, match="invalid port"):
        client.invoke(
            "algorithm.run",
            {"catalog_version": "cat_fixture", "component_version": "1.0", "algorithm": "vqe"},
        )


def test_provider_accepts_https_loopback(monkeypatch) -> None:
    monkeypatch.setenv("COMPANY_QUANTUM_PLATFORM_INVOKE_URL", "https://localhost:1/invoke")
    client = client_by_provider("uniqon")
    assert client.endpoint() == "https://localhost:1/invoke"


def test_provider_requires_https_off_loopback(monkeypatch) -> None:
    monkeypatch.setenv("COMPANY_QUANTUM_PLATFORM_INVOKE_URL", "http://example.invalid/invoke")
    client = client_by_provider("uniqon")
    assert client.configured() is False
    with pytest.raises(ProviderError, match="must use HTTPS"):
        client.invoke(
            "algorithm.run",
            {"catalog_version": "cat_fixture", "component_version": "1.0", "algorithm": "vqe"},
        )
