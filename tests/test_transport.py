from __future__ import annotations

import pytest

from sai_cli.errors import ConfigError
from sai_cli.transport import normalize_base_url, sanitize_message


@pytest.mark.parametrize(
    "url",
    [
        "http://example.org",
        "https://user:password@example.org",
        "https://example.org?token=value",
        "file:///tmp/service",  # public-scan: allow-test-vector
    ],
)
def test_base_url_rejects_insecure_or_credentialed_values(url: str) -> None:
    with pytest.raises(ConfigError):
        normalize_base_url(url, allow_insecure_http=False)


@pytest.mark.parametrize("url", ["http://127.0.0.1:8000", "http://[::1]:8000", "http://localhost:8000"])
def test_base_url_allows_loopback_http(url: str) -> None:
    assert normalize_base_url(url, allow_insecure_http=False) == url


def test_error_message_redacts_credentials_paths_and_private_addresses() -> None:
    raw = (
        "Authorization: Bearer abc.def token=secret-value "
        "path /home/user/private address 192.168.1.10"  # public-scan: allow-test-vector
    )
    sanitized = sanitize_message(raw, fallback="fallback")
    assert "abc.def" not in sanitized
    assert "secret-value" not in sanitized
    assert "/home/user" not in sanitized  # public-scan: allow-test-vector
    assert "192.168.1.10" not in sanitized  # public-scan: allow-test-vector
    assert "[redacted]" in sanitized
