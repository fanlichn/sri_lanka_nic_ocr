"""Tests for the remote URL fetch helper (no real network calls)."""
from __future__ import annotations

import socket

import pytest

from app.url_fetch import UrlFetchError, validate_url


def _fake_resolve(ip: str):
    def _getaddrinfo(host, port, proto=0):
        return [(socket.AF_INET, None, None, "", (ip, port))]

    return _getaddrinfo


def test_reject_non_http_scheme():
    with pytest.raises(UrlFetchError):
        validate_url("ftp://example.com/a.jpg", allow_private=False)
    with pytest.raises(UrlFetchError):
        validate_url("file:///etc/passwd", allow_private=False)


def test_reject_missing_hostname():
    with pytest.raises(UrlFetchError):
        validate_url("https:///a.jpg", allow_private=False)


def test_reject_loopback_host():
    with pytest.raises(UrlFetchError):
        validate_url("http://127.0.0.1:8000/a.jpg", allow_private=False)


def test_reject_private_host(monkeypatch):
    monkeypatch.setattr("app.url_fetch.socket.getaddrinfo", _fake_resolve("192.168.1.10"))
    with pytest.raises(UrlFetchError):
        validate_url("http://internal.example.com/a.jpg", allow_private=False)


def test_allow_private_when_enabled(monkeypatch):
    monkeypatch.setattr("app.url_fetch.socket.getaddrinfo", _fake_resolve("10.0.0.5"))
    assert validate_url("http://internal.example.com/a.jpg", allow_private=True)


def test_public_host_ok(monkeypatch):
    monkeypatch.setattr("app.url_fetch.socket.getaddrinfo", _fake_resolve("8.8.8.8"))
    url = "https://lak-pic.oss-ap-southeast-1.aliyuncs.com/attachment/a.jpg"
    assert validate_url(url, allow_private=False) == url
