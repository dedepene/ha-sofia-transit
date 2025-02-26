import time
import aiohttp
import logging
from urllib.parse import unquote
from typing import Any

_LOGGER = logging.getLogger(__name__)
TOKEN_LIFESPAN: int = 3600  # 2 hours tokens lifespan - 7200 sec
sofiatraffic_session_cookie: str | None = None
sofiatraffic_xsrf_token: str | None = None
tokens_last_refreshed: float | None = None


def reset_tokens() -> None:
    """Reset token values to force a fresh fetch."""
    global sofiatraffic_session_cookie, sofiatraffic_xsrf_token, tokens_last_refreshed
    sofiatraffic_session_cookie = None
    sofiatraffic_xsrf_token = None
    tokens_last_refreshed = None


async def async_fetch_tokens(session: aiohttp.ClientSession) -> None:
    """Asynchronously fetch and update tokens from SofiaTraffic."""
    global sofiatraffic_session_cookie, sofiatraffic_xsrf_token, tokens_last_refreshed  # noqa: PLW0603
    async with session.head(
        "https://sofiatraffic.bg/bg/public-transport", allow_redirects=False
    ) as response:
        cookies = response.headers.getall("Set-Cookie", [])
    for cookie in cookies:
        if cookie.startswith("XSRF-TOKEN="):
            sofiatraffic_xsrf_token = unquote(cookie.split(";", 1)[0].split("=", 1)[1])
        elif cookie.startswith("sofia_traffic_session="):
            sofiatraffic_session_cookie = unquote(
                cookie.split(";", 1)[0].split("=", 1)[1]
            )
    tokens_last_refreshed = time.time()
    _LOGGER.debug(
        "xsrf-token: %s  session cookie: %s",
        sofiatraffic_xsrf_token,
        sofiatraffic_session_cookie,
    )


async def async_fetch_data_from_sofiatraffic(
    url: str, session: aiohttp.ClientSession, body: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Asynchronously fetch data from SofiaTraffic with token renewal retry."""
    if body is None:
        body = {"stop": "1287"}
    if (
        sofiatraffic_session_cookie is None
        or sofiatraffic_xsrf_token is None
        or tokens_last_refreshed is None
        or (time.time() - tokens_last_refreshed > TOKEN_LIFESPAN)
    ):
        await async_fetch_tokens(session)
    max_attempts = 2
    for attempt in range(max_attempts):  # noqa: RET503
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:127.0) Gecko/20100101 Firefox/134.0",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-GB,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/json",
            "X-XSRF-TOKEN": sofiatraffic_xsrf_token or "",
            "Cookie": f"XSRF-TOKEN={sofiatraffic_xsrf_token or ''}; sofia_traffic_session={sofiatraffic_session_cookie or ''}",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "Priority": "u=1",
            "Pragma": "no-cache",
            "Cache-Control": "no-cache",
            "Referer": "https://www.sofiatraffic.bg/bg/public-transport",
            "TE": "trailers",
        }
        async with session.post(url, headers=headers, json=body) as response:
            content_type = response.headers.get("Content-Type", "")
            if "application/json" in content_type:
                return await response.json()
            # text = await response.text()
            error_msg = (
                f"Unexpected content type: {content_type}. Forcing a token refresh..."
            )
            # If the response is not as expected, force a complete token reset and refresh
            if attempt < max_attempts - 1:
                reset_tokens()
                await async_fetch_tokens(session)
            else:
                raise ValueError(error_msg)
