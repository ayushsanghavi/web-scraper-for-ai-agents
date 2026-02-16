"""Runtime configuration for the scraping pipeline."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse


DEFAULT_USER_AGENT = "ai-scraper/1.0 (+https://github.com/ayushsanghavi/ai-scraper)"


@dataclass(slots=True)
class CrawlConfig:
    """Validated runtime configuration for a scrape run."""

    start_url: str
    output_path: str
    max_pages: int = 100
    max_depth: int = 2
    delay_seconds: float = 0.5
    request_timeout_seconds: float = 10.0
    user_agent: str = DEFAULT_USER_AGENT
    allowed_path_prefix: str | None = None
    allowed_path_regex: str | None = None
    max_retries: int = 2
    retry_backoff_seconds: float = 0.5
    parser_backend: str = "beautifulsoup"

    def __post_init__(self) -> None:
        parsed = urlparse(self.start_url)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("start_url must use http or https")
        if not parsed.netloc:
            raise ValueError("start_url must include a valid domain")

        if not self.output_path.strip():
            raise ValueError("output_path cannot be empty")
        if self.max_pages <= 0:
            raise ValueError("max_pages must be greater than 0")
        if self.max_depth < 0:
            raise ValueError("max_depth must be 0 or greater")
        if self.delay_seconds < 0:
            raise ValueError("delay_seconds cannot be negative")
        if self.request_timeout_seconds <= 0:
            raise ValueError("request_timeout_seconds must be greater than 0")
        if self.max_retries < 0:
            raise ValueError("max_retries cannot be negative")
        if self.retry_backoff_seconds < 0:
            raise ValueError("retry_backoff_seconds cannot be negative")
        if self.parser_backend not in {"beautifulsoup", "trafilatura"}:
            raise ValueError("parser_backend must be 'beautifulsoup' or 'trafilatura'")

        if self.allowed_path_prefix:
            normalized_prefix = self.allowed_path_prefix.strip()
            if not normalized_prefix.startswith("/"):
                raise ValueError("allowed_path_prefix must start with '/'")
            self.allowed_path_prefix = normalized_prefix

        if self.allowed_path_regex:
            try:
                re.compile(self.allowed_path_regex)
            except re.error as e:
                raise ValueError(f"allowed_path_regex is not a valid regex: {e}")

        if self.allowed_path_prefix and self.allowed_path_regex:
            raise ValueError("Use --allowed-path-prefix or --allowed-path-regex, not both")

    @classmethod
    def from_namespace(cls, args: object) -> "CrawlConfig":
        """Build validated config from argparse namespace-like object."""

        return cls(
            start_url=str(getattr(args, "start_url")),
            output_path=str(getattr(args, "output")),
            max_pages=int(getattr(args, "max_pages")),
            max_depth=int(getattr(args, "max_depth")),
            delay_seconds=float(getattr(args, "delay_seconds")),
            request_timeout_seconds=float(getattr(args, "timeout")),
            user_agent=str(getattr(args, "user_agent")),
            allowed_path_prefix=getattr(args, "allowed_path_prefix"),
            allowed_path_regex=getattr(args, "allowed_path_regex", None),
            max_retries=int(getattr(args, "max_retries")),
            retry_backoff_seconds=float(getattr(args, "retry_backoff_seconds")),
            parser_backend=str(getattr(args, "parser_backend", "beautifulsoup")),
        )
