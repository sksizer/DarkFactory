"""Tests for secrets filtering utility."""

from __future__ import annotations

from darkfactory.utils.secrets import RedactionResult, redact, scan


def test_scan_finds_github_token() -> None:
    text = "token is ghp_aBcDeFgHiJkLmNoPqRsTuVwXyZaBcDeFgHiJkL"
    hits = scan(text)
    assert any(name == "github_token" for name, _ in hits)


def test_scan_finds_aws_access_key() -> None:
    text = "key=AKIAIOSFODNN7EXAMPLE"
    hits = scan(text)
    assert any(name == "aws_access_key" for name, _ in hits)


def test_scan_finds_private_key_header() -> None:
    text = "-----BEGIN RSA PRIVATE KEY-----\nMIIEpA..."
    hits = scan(text)
    assert any(name == "private_key" for name, _ in hits)


def test_scan_finds_bearer_token() -> None:
    text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.payload.sig"
    hits = scan(text)
    assert any(name == "bearer_token" for name, _ in hits)


def test_scan_finds_connection_string() -> None:
    text = "DATABASE_URL=postgres://user:pass@host:5432/db"
    hits = scan(text)
    assert any(name == "connection_string" for name, _ in hits)


def test_scan_finds_generic_api_key() -> None:
    text = "api_key: sk-abc123def456ghi789jkl012mno345pqr678"
    hits = scan(text)
    assert any(name == "generic_api_key" for name, _ in hits)


def test_scan_returns_empty_for_clean_text() -> None:
    text = "This is just a normal log line with no secrets."
    hits = scan(text)
    assert hits == []


def test_redact_replaces_github_token() -> None:
    text = "Using token ghp_aBcDeFgHiJkLmNoPqRsTuVwXyZaBcDeFgHiJkL for auth"
    result = redact(text)
    assert "ghp_" not in result.text
    assert "[REDACTED:github_token]" in result.text
    assert result.redaction_count >= 1
    assert "github_token" in result.patterns_matched


def test_redact_handles_multiple_patterns() -> None:
    text = "key=AKIAIOSFODNN7EXAMPLE token=ghp_aBcDeFgHiJkLmNoPqRsTuVwXyZaBcDeFgHiJkL"
    result = redact(text)
    assert result.redaction_count >= 2
    assert "AKIA" not in result.text
    assert "ghp_" not in result.text


def test_redact_preserves_clean_text() -> None:
    text = "Normal log output: 2026-04-10 workflow completed"
    result = redact(text)
    assert result.text == text
    assert result.redaction_count == 0
    assert result.patterns_matched == []


def test_redact_returns_result_type() -> None:
    result = redact("clean text")
    assert isinstance(result, RedactionResult)
