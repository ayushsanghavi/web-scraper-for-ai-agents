"""Tests for document enrichment."""

import json
from datetime import datetime, timezone

from ai_scraper.enricher import DocumentEnricher


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
