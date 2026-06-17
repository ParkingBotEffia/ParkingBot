"""Fetch the EFFIA search page HTML.

Deliberately tiny: one GET with a browser-like User-Agent. The availability
signal is in the server-rendered HTML, so there is no JavaScript to execute and
no headless browser to manage.
"""

from __future__ import annotations

import requests

from . import config


def fetch_search_html(url: str | None = None) -> str:
    """Return the raw HTML of the subscription search page.

    Raises requests.HTTPError on a non-2xx response so the caller (and the CI
    run) fails loudly rather than silently parsing an error page.
    """
    url = url or config.SEARCH_URL
    response = requests.get(
        url,
        headers={"User-Agent": config.USER_AGENT},
        timeout=config.HTTP_TIMEOUT,
    )
    response.raise_for_status()
    return response.text
