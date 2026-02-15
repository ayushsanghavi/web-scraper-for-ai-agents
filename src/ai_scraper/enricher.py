"""Document enrichment layer — transforms ParseResults into AIDocuments.

Takes the raw extraction output from the parser and computes all metadata,
quality signals, and classification fields that downstream need to filter, rank, and consume documents
without ever re-parsing the original HTML.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone

from ai_scraper.models import AIDocument
from ai_scraper.parser import ParseResult
from ai_scraper.utils import generate_doc_id, get_domain

logger = logging.getLogger("ai_scraper")

# Average adult reading speed in words per minute (Brysbaert 2019).
_READING_WPM = 238

# If more than half the extracted text came from <pre>/<code> blocks,
# the page is predominantly code rather than prose.
_CODE_RATIO_THRESHOLD = 0.5

# Word-count boundaries for automatic tagging.
_SHORT_CONTENT_THRESHOLD = 100
_LONG_FORM_THRESHOLD = 1000


class DocumentEnricher:
    """Compute metadata and quality signals for a single parsed page.

    Stateless — one instance can enrich any number of documents.
    """

    def enrich(
        self,
        parse_result: ParseResult,
        url: str,
        fetched_at: datetime | None = None,
    ) -> AIDocument:
        """Build a fully-populated modeled AIDocument obj from parser output.

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
            content_type=self._classify_content(parse_result, word_count),
            reading_time_minutes=self._reading_time(word_count),
            is_mostly_code=self._is_mostly_code(parse_result, char_count),
            quality_signals=self._quality_signals(parse_result, word_count, char_count),
            tags=self._auto_tags(parse_result, word_count, char_count),
            raw_metadata=dict(parse_result.meta),
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
    def _classify_content(result: ParseResult, word_count: int) -> str:
        """Heuristic page-type classification.

        Rules (applied in priority order):
        - High code ratio  → "doc_page"   (technical documentation / tutorials)
        - Long prose        → "article"    (blog posts, guides, essays)
        - Short + many links → "listing"   (index / catalog / hub pages)
        - Everything else   → "unknown"
        """

        char_count = len(result.body_text)

        if char_count > 0 and result.code_text_length / char_count > 0.3:
            return "doc_page"
        if word_count >= _LONG_FORM_THRESHOLD:
            return "article"
        if word_count < _SHORT_CONTENT_THRESHOLD and len(result.links_internal) > 10:
            return "listing"

        return "unknown"

    @staticmethod
    def _reading_time(word_count: int) -> int:

        if word_count == 0:
            return 0
        return max(1, math.ceil(word_count / _READING_WPM))

    @staticmethod
    def _is_mostly_code(result: ParseResult, char_count: int) -> bool:
        """True when code blocks dominate the page content."""

        if char_count == 0:
            return False
        return result.code_text_length / char_count > _CODE_RATIO_THRESHOLD

    @staticmethod
    def _quality_signals(
        result: ParseResult, word_count: int, char_count: int
    ) -> dict[str, float]:
        """Numeric signals useful for ranking and filtering.

        text_to_html_ratio : float
            Higher = cleaner extraction.  Values below ~0.05 often indicate
            the parser grabbed mostly boilerplate.

        link_density : float
            Links per 100 words.  Hub/index pages score high; content pages
            score low.  Useful as a negative ranking signal.

        avg_word_length : float
            Proxy for content sophistication.  Very low values (~2-3) may
            indicate junk tokens that slipped through cleaning.
        """

        signals: dict[str, float] = {}

        if result.html_length > 0:
            signals["text_to_html_ratio"] = round(char_count / result.html_length, 4)
        else:
            signals["text_to_html_ratio"] = 0.0

        if word_count > 0:
            signals["link_density"] = round(
                len(result.links_internal) / word_count * 100, 2
            )
        else:
            signals["link_density"] = 0.0

        if word_count > 0:
            signals["avg_word_length"] = round(char_count / word_count, 2)
        else:
            signals["avg_word_length"] = 0.0

        return signals

    @staticmethod
    def _auto_tags(
        result: ParseResult, word_count: int, char_count: int
    ) -> list[str]:
        """Generate automatic labels based on content characteristics."""

        tags: list[str] = []

        # Code presence.
        if result.code_text_length > 0:
            tags.append("has-code")

        # Length buckets.
        if word_count < _SHORT_CONTENT_THRESHOLD:
            tags.append("short-content")
        elif word_count >= _LONG_FORM_THRESHOLD:
            tags.append("long-form")

        if char_count > 0 and result.code_text_length / char_count > _CODE_RATIO_THRESHOLD:
            tags.append("code-heavy")

        # Metadata richness.
        if len(result.meta) >= 3:
            tags.append("metadata-rich")

        return sorted(tags)
