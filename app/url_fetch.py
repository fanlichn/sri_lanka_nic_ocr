"""Safely download images from remote URLs (e.g. Aliyun OSS, S3, CDN).

Security measures:
* only ``http`` / ``https`` schemes are allowed;
* the hostname is resolved and private / loopback / link-local /
  reserved / multicast addresses are rejected (SSRF protection,
  can be disabled via ``url_fetch_allow_private_hosts``);
* Content-Type must be an image (``application/octet-stream`` and an
  empty type are tolerated because some buckets serve that way);
* download size is capped at ``max_upload_bytes`` and reads are
  streamed so an oversized file aborts early;
* a per-request timeout guards against slow-loris style downloads.
"""
from __future__ import annotations

import ipaddress
import socket
import urllib.error
import urllib.parse
import urllib.request

from .config import Settings

_ALLOWED_SCHEMES = {"http", "https"}
# Content types that are accepted even though they don't start with "image/"
_LENIENT_TYPES = {"", "application/octet-stream", "binary/octet-stream"}


class UrlFetchError(ValueError):
    """Raised when a remote image URL cannot be fetched safely."""


def _default_port(parsed: urllib.parse.ParseResult) -> int:
    if parsed.port:
        return parsed.port
    return 443 if parsed.scheme == "https" else 80


def validate_url(url: str, *, allow_private: bool = False) -> str:
    """Validate the URL and (optionally) reject private-network hosts.

    Returns the validated URL; raises :class:`UrlFetchError` otherwise.
    """
    try:
        parsed = urllib.parse.urlparse(url)
    except ValueError as exc:  # malformed url
        raise UrlFetchError(f"无效的 URL: {exc}") from exc

    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise UrlFetchError("仅支持 http/https 图片链接")
    if not parsed.hostname:
        raise UrlFetchError("URL 缺少主机名")

    if not allow_private:
        try:
            infos = socket.getaddrinfo(
                parsed.hostname, _default_port(parsed), proto=socket.IPPROTO_TCP
            )
        except OSError as exc:
            raise UrlFetchError(f"无法解析主机: {parsed.hostname}") from exc
        for info in infos:
            try:
                ip = ipaddress.ip_address(info[4][0])
            except ValueError:  # pragma: no cover - unusual getaddrinfo result
                continue
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_reserved
                or ip.is_multicast
                or ip.is_unspecified
            ):
                raise UrlFetchError("禁止访问内网/私有地址")

    return url


def fetch_image_bytes(url: str, settings: Settings) -> bytes:
    """Download the image at ``url`` and return its bytes.

    Raises :class:`UrlFetchError` with a human-readable message on any
    problem (bad URL, non-image content, oversized file, timeout...).
    """
    url = validate_url(url, allow_private=settings.url_fetch_allow_private_hosts)

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "sri-lanka-nic-ocr/1.0",
            # Some CDNs return different content depending on Accept
            "Accept": "image/*,*/*;q=0.8",
        },
    )

    max_bytes = settings.max_upload_bytes
    chunks: list[bytes] = []
    total = 0
    try:
        with urllib.request.urlopen(
            req, timeout=settings.url_fetch_timeout_seconds
        ) as resp:
            ctype = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            if ctype not in _LENIENT_TYPES and not ctype.startswith("image/"):
                raise UrlFetchError(f"URL 未返回图片（Content-Type: {ctype}）")
            while True:
                chunk = resp.read(256 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise UrlFetchError("图片过大")
                chunks.append(chunk)
    except UrlFetchError:
        raise
    except urllib.error.HTTPError as exc:
        raise UrlFetchError(f"下载失败: HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise UrlFetchError(f"下载失败: {exc}") from exc

    data = b"".join(chunks)
    if not data:
        raise UrlFetchError("下载内容为空")
    return data
