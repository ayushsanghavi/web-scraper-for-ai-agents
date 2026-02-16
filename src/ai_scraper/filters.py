"""URL filtering layer — decides which discovered links enter the crawl queue.

Every URL discovered by the parser passes through URLFilter.should_crawl()
before being added to the queue.  This keeps all accept/reject logic in
one place rather than scattering it across the crawler.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

from ai_scraper.config import CrawlConfig

logger = logging.getLogger("ai_scraper")

# File extensions that are never HTML content pages.
# We check against the URL path suffix to avoid fetching binary resources.
_SKIP_EXTENSIONS = frozenset({
    ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico",
    ".css", ".js", ".xml", ".rss", ".atom",
    ".zip", ".tar", ".gz", ".bz2", ".7z", ".rar",
    ".mp3", ".mp4", ".wav", ".avi", ".mov", ".webm",
    ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".woff", ".woff2", ".ttf", ".eot",
    ".json", ".csv", ".tsv",
})

# URL path segments that almost never lead to useful content.
_NON_CONTENT_PATTERNS = re.compile(
    r"/(?:"
    r"login|logout|signin|signup|register|reset-password"
    r"|search|admin|dashboard|settings|preferences"
    r"|api/|cgi-bin/|wp-admin|wp-json"
    r"|cart|checkout|account|billing"
    r"|print/|raw/|edit/|action="
    r")(?:/|$|\?)",
    re.IGNORECASE,
)


class URLFilter:
    """Decides whether a discovered URL should be added to the crawl queue.

    Applies five checks in order
        1. Duplicate
        2. Unwanted File extension
        3. Non-content pattern — login, search, admin, dashboard, settings
        4. Path prefix — outside the allowed section of the site
        5. Path regex — does not match the allowed pattern
    """

    def __init__(self, config: CrawlConfig) -> None:
        self._allowed_prefix = config.allowed_path_prefix
        self._allowed_regex = re.compile(config.allowed_path_regex) if config.allowed_path_regex else None
        self._seen: set[str] = set()

    def should_crawl(self, url: str) -> bool:
        """Return True if the URL should be added to the crawl frontier."""
        if url in self._seen:
            return False
        self._seen.add(url)

        parsed = urlparse(url)
        path = parsed.path.lower()

        if self._has_skip_extension(path):
            logger.debug("Skipped (extension): %s", url)
            return False

        if _NON_CONTENT_PATTERNS.search(parsed.path):
            logger.debug("Skipped (non-content pattern): %s", url)
            return False

        if self._allowed_prefix and not path.startswith(self._allowed_prefix.lower()):
            logger.debug("Skipped (prefix mismatch): %s", url)
            return False

        if self._allowed_regex and not self._allowed_regex.search(parsed.path):
            logger.debug("Skipped (regex mismatch): %s", url)
            return False

        return True

    def mark_seen(self, url: str) -> None:
        """Record a URL as seen without running the full filter.

        Used by the crawler to register the seed URL and any URLs loaded
        from a previous run (for idempotency).
        """
        self._seen.add(url)

    @property
    def seen_count(self) -> int:
        """Number of unique URLs that have been seen so far."""
        return len(self._seen)

    @staticmethod
    def _has_skip_extension(path: str) -> bool:
        """Check if the URL path ends with a non-HTML file extension."""

        # Find the last dot in the final path segment.
        last_segment = path.rsplit("/", 1)[-1]
        dot_pos = last_segment.rfind(".")
        if dot_pos == -1:
            return False

        ext = last_segment[dot_pos:]
        return ext in _SKIP_EXTENSIONS
