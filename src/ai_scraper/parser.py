"""Content extraction layer with pluggable parser backends.

Supports two backends behind a common Protocol:
  - BeautifulSoup  — custom heuristic algorithm using BeautifulSoup
  - TrafilaturaParser - wraps the trafilatura library

The crawler selects a backend via ``create_parser()`` andwe are abstracting it - it should
not know which library is being used
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from ai_scraper.config import CrawlConfig
from ai_scraper.utils import get_domain, normalize_url

logger = logging.getLogger("ai_scraper")

@dataclass(frozen=True, slots=True)
class ParseResult:

    title: str
    body_text: str
    links_internal: list[str]
    meta: dict[str, str]
    html_length: int            # raw HTML length (for text-to-html ratio)

class ContentParser(Protocol):
    """Interface that both parser backends implement."""

    def parse(self, html: str, url: str) -> ParseResult | None: ...

# BeautifulSoup parser

# Tags that are removed before content extraction.
_NOISE_TAGS = {"script", "style", "nav", "header", "footer", "aside", "noscript"}

# Class/id substrings that mark boilerplate containers.
_NOISE_PATTERNS = re.compile(
    r"sidebar|menu|nav|footer|header|cookie|popup|modal|advertisement|social|widget|banner",
    re.IGNORECASE,
)

# Selectors tried in priority order to locate the main content container.
# The first match wins.
_CONTENT_SELECTORS = [
    "main",
    "article",
    "[role=main]",
    "div.content", "div.main", "div.body", "div.article", "div.post",
    "div#content", "div#main", "div#body", "div#article", "div#post",
]

# Separators commonly used between the page title and the site name.
_TITLE_SEP = re.compile(r"\s*[\|–—\-:]\s*")


class BSoupParser:
    """Content extraction using BeautifulSoup with custom heuristics.

    Algorithm:
        1. Remove noise tags (script, nav, footer, sidebar, etc.)
        2. Locate the main content container via semantic selectors
        3. Extract and clean body text
        4. Extract links and metadata from the full page
    """

    def __init__(self, seed_domain: str) -> None:
        self._seed_domain = seed_domain

    def parse(self, html: str, url: str) -> ParseResult | None:
        soup = BeautifulSoup(html, "lxml")

        # --- Step 1: strip noise ---
        self._remove_noise(soup)

        # --- Step 2: find main content container ---
        container = self._find_main_content(soup)

        # --- Step 3: extract and clean text ---
        body_text = self._extract_text(container)
        if not body_text:
            logger.debug("No body text extracted from %s", url)
            return None

        # --- Step 4: title, links, metadata ---
        title = self._extract_title(soup)
        links = self._extract_links(soup, url)
        meta = self._extract_meta(soup)

        return ParseResult(
            title=title,
            body_text=body_text,
            links_internal=links,
            meta=meta,
            html_length=len(html),
        )

    # internals

    @staticmethod
    def _remove_noise(soup: BeautifulSoup) -> None:
        """Decompose tags and containers that are never main content."""

        # Remove guaranteed-noise tags.
        for tag_name in _NOISE_TAGS:
            for tag in soup.find_all(tag_name):
                tag.decompose()

        # Remove containers whose class or id matches boilerplate patterns.
        # Collect first, then decompose — avoids mutating the tree during iteration.
        boilerplate: list[Tag] = []
        for tag in soup.find_all(True):
            if tag.attrs is None:
                continue
            class_str = " ".join(tag.get("class", []))
            id_str = tag.get("id", "")
            if _NOISE_PATTERNS.search(class_str) or _NOISE_PATTERNS.search(id_str):
                boilerplate.append(tag)
        for tag in boilerplate:
            tag.decompose()

    @staticmethod
    def _find_main_content(soup: BeautifulSoup) -> Tag:
        """Locate the main content container using semantic selectors."""

        for selector in _CONTENT_SELECTORS:
            match = soup.select_one(selector)
            if match and match.get_text(strip=True):
                return match

        # Fallback: the entire <body>, or the whole soup if no body tag.
        return soup.body or soup

    @staticmethod
    def _extract_text(container: Tag) -> str:
        """Get clean text from a DOM subtree."""

        raw = container.get_text(separator="\n")

        # Collapse runs of whitespace within each line.
        lines = [" ".join(line.split()) for line in raw.splitlines()]

        # Drop blank lines, then rejoin with single newlines.
        cleaned = "\n".join(line for line in lines if line)

        return cleaned.strip()

    @staticmethod
    def _extract_title(soup: BeautifulSoup) -> str:
        """Pull a clean page title, stripping the site-name suffix."""

        title_tag = soup.find("title")
        if title_tag and title_tag.string:

            parts = _TITLE_SEP.split(title_tag.string.strip())
            if parts:
                return parts[0].strip()

        # Fallback: first <h1>.
        h1 = soup.find("h1")
        if h1:
            return h1.get_text(strip=True)

        return ""

    def _extract_links(self, soup: BeautifulSoup, page_url: str) -> list[str]:
        """Collect deduplicated internal links from the page."""

        seen: set[str] = set()
        links: list[str] = []

        for anchor in soup.find_all("a", href=True):
            href = anchor["href"]

            # Skip non-HTTP schemes (mailto:, javascript:, etc.)
            if href.startswith(("mailto:", "javascript:", "tel:", "#")):
                continue

            absolute = urljoin(page_url, href)
            normalized = normalize_url(absolute)

            # Keep only same-domain links.
            if get_domain(normalized) != self._seed_domain:
                continue

            if normalized not in seen:
                seen.add(normalized)
                links.append(normalized)

        return links

    @staticmethod
    def _extract_meta(soup: BeautifulSoup) -> dict[str, str]:
        """Capture useful <meta> tags as a flat dictionary."""

        meta: dict[str, str] = {}

        tag_map = {
            "description": "description",
            "keywords": "keywords",
            "author": "author",
        }

        for name, key in tag_map.items():
            tag = soup.find("meta", attrs={"name": name})
            if tag and tag.get("content"):
                meta[key] = tag["content"].strip()

        # Open Graph title (often cleaner than <title>).
        og_title = soup.find("meta", attrs={"property": "og:title"})
        if og_title and og_title.get("content"):
            meta["og_title"] = og_title["content"].strip()

        return meta


# Trafilatura parser - https://trafilatura.readthedocs.io/en/latest/

class TrafilaturaParser:
    """Content extraction backed by the trafilatura library.

    Trafilatura uses a trained algorithm.
    """

    def __init__(self, seed_domain: str) -> None:
        self._seed_domain = seed_domain

    def parse(self, html: str, url: str) -> ParseResult | None:
        import trafilatura  # only loaded when this arg is passed in CLIis selected

        result = trafilatura.bare_extraction(
            html,
            url=url,
            include_comments=False,
            include_tables=True,
            favor_precision=True,
        )

        if result is None or not getattr(result, "text", None):
            logger.debug("Trafilatura extracted nothing from %s", url)
            return None

        body_text = result.text
        title = result.title or ""

        meta: dict[str, str] = {}
        if getattr(result, "author", None):
            meta["author"] = result.author
        if getattr(result, "description", None):
            meta["description"] = result.description
        if getattr(result, "categories", None):
            meta["categories"] = str(result.categories)
        if getattr(result, "tags", None):
            meta["tags"] = str(result.tags)

        # Link discovery via lxml (fast, no BeautifulSoup overhead).
        links = self._extract_links_lxml(html, url)

        return ParseResult(
            title=title,
            body_text=body_text,
            links_internal=links,
            meta=meta,
            html_length=len(html),
        )

    def _extract_links_lxml(self, html: str, page_url: str) -> list[str]:
        """Extract internal links using lxml for speed."""

        from lxml import html as lxml_html

        try:
            doc = lxml_html.fromstring(html)
        except Exception:
            return []

        seen: set[str] = set()
        links: list[str] = []

        for element in doc.iter("a"):
            href = element.get("href")
            if not href or href.startswith(("mailto:", "javascript:", "tel:", "#")):
                continue

            absolute = urljoin(page_url, href)
            normalized = normalize_url(absolute)

            if get_domain(normalized) != self._seed_domain:
                continue

            if normalized not in seen:
                seen.add(normalized)
                links.append(normalized)

        return links



# Quality scorer — used by compare mode and potential future auto-selection

def score_parse_result(result: ParseResult) -> float:
    """Score a ParseResult on a 0-to-1 scale for quality comparison.

    Weights reflect what matters for AI-ready documents:
    - Body length is the strongest signal (did we get real content?)
    - Text-to-HTML ratio indicates extraction precision
    - Title presence and metadata richness are secondary signals
    """

    score = 0.0

    # Body text length (0.0 – 0.4 points).
    # 500+ chars is "full content"; fewer scales linearly.
    text_len = len(result.body_text)
    score += min(text_len / 500, 1.0) * 0.4

    # Text-to-HTML ratio (0.0 – 0.3 points).
    # Higher ratio = cleaner extraction.
    if result.html_length > 0:
        ratio = text_len / result.html_length
        score += min(ratio / 0.3, 1.0) * 0.3

    # Title present (0.15 points).
    if result.title:
        score += 0.15

    # Metadata richness (0.0 – 0.15 points).
    meta_count = len(result.meta)
    score += min(meta_count / 3, 1.0) * 0.15

    return round(score, 3)


# Factory

_BACKENDS = {"beautifulsoup", "trafilatura"}


def create_parser(backend: str, config: CrawlConfig) -> ContentParser:
    """Instantiate a parser backend by name.

    Raises ValueError for unknown backend names so typos are caught early.
    """

    seed_domain = get_domain(config.start_url)

    if backend == "beautifulsoup":
        return BSoupParser(seed_domain)

    if backend == "trafilatura":
        return TrafilaturaParser(seed_domain)

    raise ValueError(
        f"Unknown parser backend {backend!r}. Choose from: {', '.join(sorted(_BACKENDS))}"
    )
