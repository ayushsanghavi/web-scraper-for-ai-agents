"""Shared util functions used across other classes."""

from __future__ import annotations
import hashlib
import logging
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

# Tracking parameters injected by analytics platforms.
# These never change page content, so we strip them during normalization
# to avoid treating the same page as two different documents.
_TRACKING_PARAMS = frozenset({
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "ref"
})

# Default ports that add no information to the URL.
_DEFAULT_PORTS = {"http": 80, "https": 443}


def normalize_url(url: str) -> str:
    """Normalize a URL so that equivalent addresses produce the same string.

    Handles: fragment removal, scheme/host lowercasing, default port stripping,
    query param sorting, and tracking parameter removal.
    """

    parsed = urlparse(url)

    scheme = parsed.scheme.lower()
    host = parsed.hostname or ""
    host = host.lower()

    # Drop the port if it matches the scheme's default (e.g. :443 on https).
    port = parsed.port
    if port and port == _DEFAULT_PORTS.get(scheme):
        port = None
    netloc = f"{host}:{port}" if port else host

    # Preserve the path exactly, but guarantee at least a bare "/".
    path = parsed.path or "/"

    # Strip default index filenames so "/" and "/index.html" dedup.
    _INDEX_FILES = ("index.html", "index.htm", "default.html", "default.htm")
    for idx_file in _INDEX_FILES:
        if path.endswith(f"/{idx_file}"):
            path = path[: -len(idx_file)]
            break

    # Sort query parameters alphabetically and drop tracking noise.
    query_params = parse_qs(parsed.query, keep_blank_values=True)
    filtered = {
        k: v for k, v in query_params.items() if k.lower() not in _TRACKING_PARAMS
    }
    sorted_query = urlencode(filtered, doseq=True) if filtered else ""

    # Fragments are client-side only; the server returns the same response.
    return urlunparse((scheme, netloc, path, "", sorted_query, ""))


def generate_doc_id(normalized_url: str) -> str:
    """Produce a deterministic document ID from a normalized URL.

    Uses the first 16 hex characters of a SHA-256 digest
    """

    digest = hashlib.sha256(normalized_url.encode("utf-8")).hexdigest()
    return digest[:16]


def get_domain(url: str) -> str:
    """Extract the hostname from a URL.

    Returns an empty string for malformed input rather than raising,
    since callers use this in hot loops where exceptions are expensive.
    """
    return (urlparse(url).hostname or "").lower()


def setup_logging(verbose: bool = False) -> logging.Logger:
    """Configure and return the pipeline-wide logger.

    Call once from cli.main(). Every other module retrieves the same
    logger via ``logging.getLogger("ai_scraper")``.
    """

    logger = logging.getLogger("ai_scraper")

    if logger.handlers:
        return logger

    level = logging.DEBUG if verbose else logging.INFO
    logger.setLevel(level)

    handler = logging.StreamHandler()
    handler.setLevel(level)

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger
