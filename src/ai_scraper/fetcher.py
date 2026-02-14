"""HTTP fetching layer with connection pooling, retries, and timeouts.

This module is the only place in the pipeline that touches the network.
"""

from __future__ import annotations
import logging
from dataclasses import dataclass
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ai_scraper.config import CrawlConfig

logger = logging.getLogger("ai_scraper")

@dataclass(frozen=True, slots=True)
class FetchResult:
    """Outcome of a single HTTP fetch attempt.

    Every call to PageFetcher.fetch() returns one of these — the fetcher
    never raises exceptions to the caller.  The crawler checks ``success``
    and acts accordingly.
    """

    url: str                # URL we originally requested
    final_url: str          # URL after any redirects
    status_code: int        # HTTP status (0 if we never got a response)
    html: str | None        # decoded response body (None on failure)
    content_type: str       # Content-Type header value
    success: bool           # True when we have usable HTML
    error: str | None       # human-readable reason on failure

# Upper bound on response size (5 MB).  Anything larger is almost certainly
# not a normal documentation or article page.
_MAX_CONTENT_LENGTH = 5 * 1024 * 1024

# Connect timeout in seconds.  This is how long we wait for the server to
# accept the TCP connection — separate from the read timeout which covers
# how long we wait for the response body.
_CONNECT_TIMEOUT = 5.0


class PageFetcher:
    """Reusable HTTP client for the lifetime of a single crawl run.

    Holds a ``requests.Session`` for TCP connection pooling and mounts
    a retry policy on the transport adapter.
    """

    def __init__(self, config: CrawlConfig) -> None:
        self._timeout = (_CONNECT_TIMEOUT, config.request_timeout_seconds)

        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": config.user_agent,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        })

        retry = Retry(
            total=config.max_retries,
            backoff_factor=config.retry_backoff_seconds,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["GET"],
        )
        adapter = HTTPAdapter(max_retries=retry)
        self._session.mount("https://", adapter)
        self._session.mount("http://", adapter)

    def fetch(self, url: str) -> FetchResult:
        """Fetch a single URL and return a ``FetchResult``.

        Handles every failure mode internally — the caller never needs
        to wrap this in try/except.
        """

        try:
            response = self._session.get(
                url,
                timeout=self._timeout,
                allow_redirects=True,
            )
        except requests.ConnectionError:
            return self._fail(url, error="connection refused or DNS failure")
        except requests.Timeout:
            return self._fail(url, error="request timed out")
        except requests.RequestException as exc:
            return self._fail(url, error=str(exc))

        final_url = response.url
        status = response.status_code
        content_type = response.headers.get("Content-Type", "")

        if status >= 400:
            logger.debug("HTTP %d on %s", status, url)
            return self._fail(
                url,
                final_url=final_url,
                status_code=status,
                content_type=content_type,
                error=f"HTTP {status}",
            )

        if "text/html" not in content_type.lower():
            return self._fail(
                url,
                final_url=final_url,
                status_code=status,
                content_type=content_type,
                error=f"non-HTML content type: {content_type}",
            )

        length = response.headers.get("Content-Length")
        if length and int(length) > _MAX_CONTENT_LENGTH:
            return self._fail(
                url,
                final_url=final_url,
                status_code=status,
                content_type=content_type,
                error=f"response too large: {length} bytes",
            )

        html = response.text
        logger.debug("Fetched %s (%d chars)", final_url, len(html))

        return FetchResult(
            url=url,
            final_url=final_url,
            status_code=status,
            html=html,
            content_type=content_type,
            success=True,
            error=None,
        )

    def close(self) -> None:
        """Release the underlying connection pool."""
        self._session.close()

    def __enter__(self) -> PageFetcher:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


    @staticmethod
    def _fail(
        url: str,
        *,
        final_url: str | None = None,
        status_code: int = 0,
        content_type: str = "",
        error: str,
    ) -> FetchResult:
        """Build a failure FetchResult"""

        return FetchResult(
            url=url,
            final_url=final_url or url,
            status_code=status_code,
            html=None,
            content_type=content_type,
            success=False,
            error=error,
        )
