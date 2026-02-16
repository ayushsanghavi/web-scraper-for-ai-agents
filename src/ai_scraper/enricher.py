"""Document enrichment layer — transforms ParseResults into AIDocuments.

Takes the raw extraction output from the parser and computes all metadata
and classification fields that downstream. need to filter, rank,
and consume documents without ever re-parsing the original HTML.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

from ai_scraper.models import AIDocument
from ai_scraper.parser import ParseResult
from ai_scraper.utils import generate_doc_id, get_domain

logger = logging.getLogger("ai_scraper")

# ── Content-type classification ──────────────────────────────────────────────

_CONTENT_TYPES = ("article", "product", "listing", "faq", "other")

# URL path patterns that strongly suggest a specific type.
_URL_SIGNALS: list[tuple[str, re.Pattern[str]]] = [
    ("reference", re.compile(r"/(?:docs?|wiki|api|reference|manual|guide|help|kb|knowledge)[/]", re.I)),
    ("product",   re.compile(r"/(?:product|item|shop|store|catalogue/[^/]+/[^/]+)[/]", re.I)),
    ("profile",   re.compile(r"/(?:author|profile|user|about|people|team|contributor)[/s]?", re.I)),
    ("faq",       re.compile(r"/(?:faq|frequently-asked|q-and-a|questions)[/s]?", re.I)),
]

# Price-like pattern in body text (e.g. £12.84, $9.99, €5, USD 10).
_PRICE_RE = re.compile(r"(?:[$£€¥₹]|USD|EUR|GBP)\s*\d", re.I)


class DocumentEnricher:
    """Compute metadata for a single parsed page.

    Stateless — one instance can enrich any number of documents.
    """

    def enrich(
        self,
        parse_result: ParseResult,
        url: str,
        fetched_at: datetime | None = None,
    ) -> AIDocument:
        """Build a fully-populated AIDocument from parser output.

        Parameters
        ----------
        parse_result : ParseResult
            Structured extraction output from ContentParser backend.
        url : str
            The normalized URL of the page (used for doc_id and source).
        fetched_at : datetime, optional
            Timestamp of the fetch.
        """

        if fetched_at is None:
            fetched_at = datetime.now(timezone.utc)

        body = parse_result.body_text
        word_count = self._count_words(body)
        char_count = len(body)

        return AIDocument(
            doc_id=generate_doc_id(url),
            source=get_domain(url),
            url=url,
            title=parse_result.title,
            body_text=body,
            fetched_at=fetched_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            word_count=word_count,
            char_count=char_count,
            language=self._detect_language(body),
            content_type=self._classify_content(parse_result, word_count, url),
            text_to_html_ratio=self._text_to_html_ratio(parse_result, char_count),
            links_out_internal=list(parse_result.links_internal),
        )

    # Private helpers

    @staticmethod
    def _count_words(text: str) -> int:
        return len(text.split())

    @staticmethod
    def _detect_language(text: str) -> str | None:
        """Detect language using langdetect.  Returns None on failure.
        """

        if len(text.split()) < 20:
            return None

        try:
            from langdetect import detect, LangDetectException

            return detect(text)
        except LangDetectException:
            logger.debug("Language detection failed for text of length %d", len(text))
            return None
        except Exception:
            # Guard against unexpected langdetect internals failures.
            return None

    @staticmethod
    def _classify_content(result: ParseResult, word_count: int, url: str) -> str:
        """Multi-signal heuristic page-type classification.

        Scores each candidate type by combining URL path patterns, title
        keywords, and body-text features.  Highest score wins; ties are
        broken by type priority order.  Falls back to ``other``.
        """

        scores: dict[str, float] = {t: 0.0 for t in _CONTENT_TYPES}
        path = urlparse(url).path
        link_count = len(result.links_internal)

        # URL path signals
        for content_type, pattern in _URL_SIGNALS:
            if pattern.search(path):
                scores[content_type] += 3.0

        # ── Body text heuristics ──

        # Article: long-form prose with relatively few links.
        if word_count >= 300:
            link_density = link_count / max(word_count, 1)
            if link_density < 0.05:
                scores["article"] += 2.0
            if word_count >= 800:
                scores["article"] += 1.0

        # Listing: short body with many outbound links.
        if link_count > 10 and word_count < 200:
            scores["listing"] += 2.5
        elif link_count > 5 and word_count < 100:
            scores["listing"] += 2.0

        # Product: price-like patterns in body text.
        if _PRICE_RE.search(result.body_text):
            scores["product"] += 2.0

        # FAQ: question-mark density in body text.
        qmark_count = result.body_text.count("?")
        if qmark_count >= 3 and qmark_count / max(word_count, 1) > 0.01:
            scores["faq"] += 2.0

        # Pick the highest-scoring type (priority order breaks ties).
        best_type = "other"
        best_score = 0.0
        for content_type in _CONTENT_TYPES:
            if scores[content_type] > best_score:
                best_score = scores[content_type]
                best_type = content_type

        return best_type

    @staticmethod
    def _text_to_html_ratio(result: ParseResult, char_count: int) -> float:
        """Ratio of extracted text to raw HTML length.

        Higher values indicate cleaner extraction.  Values below ~0.05
        often mean the parser grabbed mostly boilerplate.
        """

        if result.html_length > 0:
            return round(char_count / result.html_length, 4)
        return 0.0
