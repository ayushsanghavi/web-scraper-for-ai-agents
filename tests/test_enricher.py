"""Tests for document enrichment."""

import json
from datetime import datetime, timezone

import pytest

from ai_scraper.enricher import DocumentEnricher
from ai_scraper.parser import ParseResult


def test_enricher_produces_complete_ai_document(sample_parse_result):
    """Enricher should populate all metadata fields
    from a ParseResult into a JSON-serializable AIDocument."""

    enricher = DocumentEnricher()
    fixed_time = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    doc = enricher.enrich(sample_parse_result, url="https://docs.com/page", fetched_at=fixed_time)

    # Core fields.
    assert doc.doc_id  # deterministic hash
    assert doc.source == "docs.com"
    assert doc.title == "Test Document"
    assert doc.fetched_at == "2026-06-01T12:00:00Z"

    assert doc.word_count > 0
    assert doc.char_count > 0

    assert doc.language == "en"

    assert doc.text_to_html_ratio > 0

    # Same URL always gives the same doc_id (idempotency).
    doc2 = enricher.enrich(sample_parse_result, url="https://docs.com/page")
    assert doc.doc_id == doc2.doc_id

    # Serializable to JSON.
    assert json.dumps(doc.to_dict())


# ── Content-type classification tests ────────────────────────────────────────

def _make_result(body: str = "Some text.", links: int = 2, title: str = "Page") -> ParseResult:
    """Helper to build a minimal ParseResult for classification tests."""
    return ParseResult(
        title=title,
        body_text=body,
        links_internal=[f"https://x.com/{i}" for i in range(links)],
        meta={},
        html_length=5000,
    )


_enricher = DocumentEnricher()


@pytest.mark.parametrize("url, body, links, title, expected", [
    # Article — long prose, few links.
    (
        "https://blog.com/posts/my-story",
        "Word " * 400,
        3,
        "My Story",
        "article",
    ),
    # Reference — URL path signal.
    (
        "https://example.com/docs/getting-started/",
        "Setup instructions. " * 30,
        5,
        "Getting Started",
        "reference",
    ),
    # Product — catalogue detail page with price.
    (
        "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/",
        "A Light in the Attic £51.77 In stock",
        4,
        "A Light in the Attic",
        "product",
    ),
    # Profile — author URL pattern.
    (
        "https://quotes.toscrape.com/author/Albert-Einstein/",
        "Albert Einstein was a theoretical physicist. " * 5,
        3,
        "Albert Einstein",
        "profile",
    ),
    # Listing — short body, many links.
    (
        "https://books.toscrape.com/",
        "Books catalogue. Browse titles below.",
        20,
        "All products",
        "listing",
    ),
    # FAQ — title keyword + question marks.
    (
        "https://example.com/faq/",
        "What is this? How does it work? Can I return it? Where do I sign up?",
        2,
        "FAQ",
        "faq",
    ),
    # Other — short generic page, no strong signals.
    (
        "https://example.com/contact",
        "Get in touch with us via email.",
        2,
        "Contact",
        "other",
    ),
], ids=["article", "reference", "product", "profile", "listing", "faq", "other"])
def test_classify_content(url, body, links, title, expected):
    result = _make_result(body=body, links=links, title=title)
    doc = _enricher.enrich(result, url=url)
    assert doc.content_type == expected, (
        f"Expected {expected!r} for {url}, got {doc.content_type!r}"
    )
