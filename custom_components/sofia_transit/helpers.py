"""Helper utilities for Sofia Traffic API calls and token handling.

This module manages fetching CSRF/session tokens and making robust API requests
with retries, backoff, and detailed debug logging.
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
import html as html_mod
import logging
import random
import re
import time
from typing import Any
from urllib.parse import unquote

import aiohttp

_LOGGER = logging.getLogger(__name__)


# Tokens are typically valid for ~2 hours on the site; refresh a bit sooner to be safe
TOKEN_LIFESPAN: int = 3600
# How many bytes of unexpected response body to log at debug level
DEBUG_LOG_BODY_BYTES: int = 512


@dataclass
class TokenState:
    """Holds SofiaTraffic XSRF/session tokens and refresh timestamp."""

    xsrf_token: str | None = None
    session_cookie: str | None = None
    last_refreshed: float | None = None
    csrf_meta_token: str | None = None


token_state = TokenState()


def reset_tokens() -> None:
    """Reset token values to force a fresh fetch."""
    token_state.xsrf_token = None
    token_state.session_cookie = None
    token_state.last_refreshed = None
    token_state.csrf_meta_token = None


def _mask(token: str | None) -> str:
    """Mask sensitive values for logs."""
    if not token:
        return "<empty>"
    if len(token) <= 8:
        return "*" * len(token)
    return f"{token[:4]}***{token[-4:]}"


def _extract_html_diagnostics(text: str) -> dict[str, object]:
    """Extract title and visible text snippet from HTML for diagnostics.

    Returns a dict with: title, text_excerpt, text_length, indicators, csrf_meta
    """
    # Title
    title_match = re.search(
        r"<title[^>]*>(.*?)</title>", text, re.IGNORECASE | re.DOTALL
    )
    title = html_mod.unescape(title_match.group(1).strip()) if title_match else None

    # CSRF meta
    csrf_match = re.search(
        r'<meta[^>]*name=["\']csrf-token["\'][^>]*content=["\']([^"\']+)["\']',
        text,
        re.IGNORECASE,
    )
    csrf_meta = csrf_match.group(1) if csrf_match else None

    # Remove script/style and tags to get visible text
    cleaned = re.sub(
        r"<(script|style)[^>]*>.*?</\\1>", " ", text, flags=re.IGNORECASE | re.DOTALL
    )
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    visible = html_mod.unescape(cleaned)

    indicators = {
        "has_captcha": bool(re.search(r"captcha|recaptcha", text, re.IGNORECASE)),
        "forbidden": bool(re.search(r"403 Forbidden", text, re.IGNORECASE)),
        "too_many_requests": bool(
            re.search(r"429|Too Many Requests", text, re.IGNORECASE)
        ),
        "not_found": bool(re.search(r"404|Not Found", text, re.IGNORECASE)),
        "cloudflare": bool(re.search(r"cloudflare|cf-ray|cf-", text, re.IGNORECASE)),
    }

    excerpt_len = min(len(visible), 8192)
    text_excerpt = visible[:excerpt_len]
    truncated = excerpt_len < len(visible)

    return {
        "title": title,
        "text_excerpt": text_excerpt,
        "text_length": len(visible),
        "truncated": truncated,
        "indicators": indicators,
        "csrf_meta": csrf_meta,
    }


async def async_fetch_tokens(session: aiohttp.ClientSession) -> None:
    """Asynchronously fetch and update tokens from SofiaTraffic.

    Proper Sanctum flow: GET /sanctum/csrf-cookie to set XSRF-TOKEN, then
    optionally warm up the session by visiting the public page.
    """
    cookies: list[str] = []
    try:
        # 1) Get CSRF cookie via Sanctum endpoint (sets XSRF-TOKEN and often session)
        async with session.get(
            "https://www.sofiatraffic.bg/sanctum/csrf-cookie",
            headers={
                "Accept": "*/*",
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:127.0) Gecko/20100101 Firefox/134.0",
                "Accept-Language": "bg-BG,bg;q=0.9,en;q=0.8",
                # Avoid brotli to keep deps minimal
                "Accept-Encoding": "identity",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": "https://www.sofiatraffic.bg/bg/public-transport",
            },
            allow_redirects=True,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as response:
            status = response.status
            cookies = response.headers.getall("Set-Cookie", [])
            _LOGGER.debug(
                "Token fetch GET(sanctum/csrf-cookie) status=%s set_cookie_count=%s",
                status,
                len(cookies),
            )

        # 2) Warm session by loading the public page (helps some backends set session)
        async with session.get(
            "https://www.sofiatraffic.bg/bg/public-transport",
            headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:127.0) Gecko/20100101 Firefox/134.0",
                "Accept-Language": "bg-BG,bg;q=0.9,en;q=0.8",
                "Accept-Encoding": "identity",
                "Upgrade-Insecure-Requests": "1",
            },
            allow_redirects=True,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as response:
            status = response.status
            cookies += response.headers.getall("Set-Cookie", [])
            _LOGGER.debug(
                "Token warm-up GET(public-transport) status=%s set_cookie_count+=%s",
                status,
                len(response.headers.getall("Set-Cookie", [])),
            )
            # Extract meta csrf token from HTML
            with contextlib.suppress(Exception):
                text = await response.text()
                diag = _extract_html_diagnostics(text)
                meta = diag.get("csrf_meta") if isinstance(diag, dict) else None
                if meta:
                    token_state.csrf_meta_token = str(meta)
    except (aiohttp.ClientError, TimeoutError) as err:
        _LOGGER.warning("Failed to fetch tokens (network error): %s", err)
        raise

    # Persist cookies
    for cookie in cookies:
        if cookie.startswith("XSRF-TOKEN="):
            token_state.xsrf_token = unquote(cookie.split(";", 1)[0].split("=", 1)[1])
        elif cookie.startswith("sofia_traffic_session="):
            token_state.session_cookie = unquote(
                cookie.split(";", 1)[0].split("=", 1)[1]
            )
    token_state.last_refreshed = time.time()

    _LOGGER.debug(
        "Fetched tokens xsrf=%s session=%s meta_csrf=%s",
        _mask(token_state.xsrf_token),
        _mask(token_state.session_cookie),
        _mask(token_state.csrf_meta_token),
    )


async def async_fetch_data_from_sofiatraffic(
    url: str,
    session: aiohttp.ClientSession,
    body: dict[str, Any] | None = None,
    *,
    max_attempts: int = 4,
) -> dict[str, Any]:
    """Fetch data from SofiaTraffic with robust retries and token handling.

    Retries on token issues (401/403), rate limiting (429), server errors (5xx),
    timeouts and unexpected content types. On each retry, uses exponential backoff
    with a small jitter to avoid thundering herd.
    """
    if body is None:
        body = {"stop": "1287"}

    # Ensure tokens are present and not stale
    if (
        token_state.session_cookie is None
        or token_state.xsrf_token is None
        or token_state.last_refreshed is None
        or (time.time() - token_state.last_refreshed > TOKEN_LIFESPAN)
    ):
        _LOGGER.debug("Tokens missing or stale, fetching fresh tokens")
        await async_fetch_tokens(session)

    # Track whether we have tried JSON payload as a fallback
    tried_json_payload = False
    for attempt in range(max_attempts):
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:127.0) Gecko/20100101 Firefox/134.0",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "bg-BG,bg;q=0.9,en;q=0.8",
            # Avoid brotli to prevent dependency on optional Brotli decoder
            "Accept-Encoding": "gzip, deflate",
            "X-Requested-With": "XMLHttpRequest",
            # Laravel endpoints often expect form-encoded body
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            # Send both tokens: cookie-based XSRF and meta csrf (if available)
            "X-XSRF-TOKEN": token_state.xsrf_token or "",
            "X-CSRF-TOKEN": token_state.csrf_meta_token or token_state.xsrf_token or "",
            "Cookie": (
                f"XSRF-TOKEN={token_state.xsrf_token or ''}; "
                f"sofia_traffic_session={token_state.session_cookie or ''}"
            ),
            "Origin": "https://www.sofiatraffic.bg",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "Priority": "u=1",
            "Pragma": "no-cache",
            "Cache-Control": "no-cache",
            "Referer": "https://www.sofiatraffic.bg/bg/public-transport",
            "TE": "trailers",
        }
        try:
            # Send as form-encoded to match typical backend expectations
            post_kwargs: dict[str, Any] = {
                "headers": headers,
                "timeout": aiohttp.ClientTimeout(total=15),
            }
            if tried_json_payload:
                # Fallback to JSON body on subsequent attempts
                post_kwargs["json"] = body
                headers["Content-Type"] = "application/json"
            else:
                post_kwargs["data"] = body
                headers["Content-Type"] = (
                    "application/x-www-form-urlencoded; charset=UTF-8"
                )

            async with session.post(url, **post_kwargs) as response:
                status = response.status
                content_type = response.headers.get("Content-Type", "")
                _LOGGER.debug(
                    "POST %s status=%s content_type=%s stop=%s attempt=%s/%s",
                    url,
                    status,
                    content_type,
                    body.get("stop"),
                    attempt + 1,
                    max_attempts,
                )

                # Update tokens if server rotated them
                for cookie in response.headers.getall("Set-Cookie", []):
                    if cookie.startswith("XSRF-TOKEN="):
                        token_state.xsrf_token = unquote(
                            cookie.split(";", 1)[0].split("=", 1)[1]
                        )
                    elif cookie.startswith("sofia_traffic_session="):
                        token_state.session_cookie = unquote(
                            cookie.split(";", 1)[0].split("=", 1)[1]
                        )

                # Handle auth issues by forcing token refresh
                if status in (401, 403):
                    _LOGGER.info("Auth failure (status %s), refreshing tokens", status)
                    reset_tokens()
                    await async_fetch_tokens(session)
                    # retry next loop iteration
                elif status == 429:
                    # Rate limited
                    retry_after = response.headers.get("Retry-After")
                    _LOGGER.warning(
                        "Rate limited (429) for stop %s, Retry-After=%s",
                        body.get("stop"),
                        retry_after,
                    )
                    # Best-effort honor Retry-After seconds if numeric
                    if retry_after and retry_after.isdigit():
                        await asyncio.sleep(int(retry_after))
                    else:
                        # Backoff a bit even without header
                        await asyncio.sleep(5)
                elif 500 <= status < 600:
                    _LOGGER.warning(
                        "Server error status=%s for stop %s",
                        status,
                        body.get("stop"),
                    )
                elif status != 200:
                    _LOGGER.warning(
                        "Unexpected status=%s for stop %s",
                        status,
                        body.get("stop"),
                    )

                if "application/json" in content_type:
                    try:
                        return await response.json()
                    except (
                        ValueError,
                        aiohttp.ContentTypeError,
                    ) as err:  # JSON parsing issue
                        _LOGGER.warning(
                            "JSON parse error for stop %s: %s",
                            body.get("stop"),
                            err,
                        )
                else:
                    # Read full text to extract diagnostics
                    try:
                        text = await response.text()
                    except (aiohttp.ClientPayloadError, UnicodeDecodeError):
                        text = "<failed to read body>"
                    diag = _extract_html_diagnostics(text)

                    # Mask any token-like values
                    csrf_val = diag.get("csrf_meta")
                    masked_csrf = _mask(str(csrf_val)) if csrf_val else None

                    # Log headers (non-sensitive subset)
                    hdr = response.headers
                    set_cookie_count = (
                        len(hdr.getall("Set-Cookie", []))
                        if hasattr(hdr, "getall")
                        else 0
                    )
                    _LOGGER.warning(
                        "Unexpected content-type=%s stop=%s title=%s html_text_len=%s truncated=%s "
                        "indicators=%s set_cookie_count=%s",
                        content_type or "<none>",
                        body.get("stop"),
                        diag.get("title"),
                        diag.get("text_length"),
                        diag.get("truncated"),
                        diag.get("indicators"),
                        set_cookie_count,
                    )
                    # Provide excerpt for quick inspection
                    excerpt = diag.get("text_excerpt") or ""
                    if excerpt:
                        level = (
                            _LOGGER.warning
                            if attempt == max_attempts - 1
                            else _LOGGER.debug
                        )
                        level("HTML excerpt: %s", excerpt)
                    if masked_csrf:
                        _LOGGER.debug(
                            "HTML meta csrf-token present (masked): %s", masked_csrf
                        )
                    # If the page likely indicates rate limit, increase backoff
                    indicators = diag.get("indicators") or {}
                    if isinstance(indicators, dict) and indicators.get(
                        "too_many_requests"
                    ):
                        # Randomized backoff between 5-10s
                        await asyncio.sleep(5 + random.random() * 5)
                    # Try switching payload format next attempt
                    if not tried_json_payload:
                        tried_json_payload = True

                # If we reached here, we'll retry if attempts remain
        except (aiohttp.ClientError, TimeoutError) as err:
            _LOGGER.warning(
                "Network error for stop %s: %s (attempt %s/%s)",
                body.get("stop"),
                err,
                attempt + 1,
                max_attempts,
            )

        # Prepare next retry (exponential backoff with jitter)
        if attempt < max_attempts - 1:
            backoff = min(8, 0.5 * (2**attempt)) + (attempt * 0.1)
            await asyncio.sleep(backoff)
            # Only refresh tokens on explicit auth errors, not on HTML content

    raise ValueError("Failed to fetch valid JSON after retries")
