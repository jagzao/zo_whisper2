"""T04-T07: bind-address policy (RFC1918 IPv4, IPv6 ULA, loopback only)."""

from __future__ import annotations

import pytest

from transcript_pipeline.errors import ConfigurationError
from transcript_pipeline.kab_ingest.bind import validate_bind_host
from transcript_pipeline.kab_ingest.settings import KabIngestSettings


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("127.0.0.1", "127.0.0.1"),
        ("127.8.8.8", "127.8.8.8"),
        ("10.1.2.3", "10.1.2.3"),
        ("172.16.0.5", "172.16.0.5"),
        ("172.31.255.255", "172.31.255.255"),
        ("192.168.1.10", "192.168.1.10"),
        ("::1", "::1"),
        ("fd00::5", "fd00::5"),
        ("fdab:cd12:34ef::1", "fdab:cd12:34ef::1"),
    ],
)
def test_t04_bind_policy_accepts_loopback_rfc1918_ula(raw, expected):
    assert validate_bind_host(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "0.0.0.0",
        "::",
        "8.8.8.8",
        "1.2.3.4",
        "172.32.0.1",
        "169.254.1.1",
        "224.0.0.1",
        "fe80::1",
        "ff02::1",
        "example.com",
        "localhost",
        "myhost",
        "",
        "   ",
        "127.0.0.1.evil.com",
    ],
)
def test_t05_bind_policy_rejects_wildcard_public_and_dns(raw):
    with pytest.raises(ConfigurationError):
        validate_bind_host(raw)


def test_t06_enabled_without_host_rejected(monkeypatch):
    for key in [k for k in __import__("os").environ if k.startswith("KAB_INGEST_")]:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("KAB_INGEST_ENABLED", "true")
    settings = KabIngestSettings.from_env()
    assert settings.enabled is True
    assert settings.host is None
    with pytest.raises(ConfigurationError):
        settings.validate_for_server()


def test_t07_env_host_parsed_through_policy(monkeypatch):
    for key in [k for k in __import__("os").environ if k.startswith("KAB_INGEST_")]:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("KAB_INGEST_ENABLED", "true")
    monkeypatch.setenv("KAB_INGEST_HOST", "192.168.7.7")
    assert KabIngestSettings.from_env().host == "192.168.7.7"
    monkeypatch.setenv("KAB_INGEST_HOST", "kab.example.net")
    with pytest.raises(ConfigurationError):
        KabIngestSettings.from_env()
