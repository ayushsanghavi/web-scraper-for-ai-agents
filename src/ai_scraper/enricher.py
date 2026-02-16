"""Document enrichment layer — transforms ParseResults into AIDocuments.

Takes the raw extraction output from the parser and computes all metadata
and classification fields that downstream. need to filter, rank,
and consume documents without ever re-parsing the original HTML.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from ai_scraper.models import AIDocument
from ai_scraper.parser import ParseResult
from ai_scraper.utils import generate_doc_id, get_domain

logger = logging.getLogger("ai_scraper")

# Word-count boundaries for content classification.
_SHORT_CONTENT_THRESHOLD = 100
_LONG_FORM_THRESHOLD = 1000


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
            content_type=self._classify_content(parse_result, word_count),
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
    def _classify_content(result: ParseResult, word_count: int) -> str:
        """Heuristic page-type classification.

        Rules (applied in priority order):
        - Long prose        → "article"    (blog posts, guides, essays)
        - Short + many links → "listing"   (index / catalog / hub pages)
        - Everything else   → "unknown"
        """

        if word_count >= _LONG_FORM_THRESHOLD:
            return "article"
        if word_count < _SHORT_CONTENT_THRESHOLD and len(result.links_internal) > 10:
            return "listing"

        return "unknown"

    @staticmethod
    def _text_to_html_ratio(result: ParseResult, char_count: int) -> float:
        """Ratio of extracted text to raw HTML length.

        Higher values indicate cleaner extraction.  Values below ~0.05
        often mean the parser grabbed mostly boilerplate.
        """

        if result.html_length > 0:
            return round(char_count / result.html_length, 4)
        return 0.0
