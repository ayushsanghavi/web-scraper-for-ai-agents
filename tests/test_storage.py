"""Tests for JSONL storage."""

from ai_scraper.enricher import DocumentEnricher
from ai_scraper.storage import JSONLStorage


def test_storage_save_and_load_roundtrip(tmp_path, sample_parse_result):
    """Save documents to JSONL, load them back, and verify nothing is lost."""

    output_file = str(tmp_path / "test.jsonl")
    storage = JSONLStorage(output_file)

    # Create two documents via the enricher.
    enricher = DocumentEnricher()
    doc1 = enricher.enrich(sample_parse_result, url="https://example.com/page1")
    doc2 = enricher.enrich(sample_parse_result, url="https://example.com/page2")

    # Save.
    count = storage.save([doc1, doc2])
    assert count == 2

    # Load back.
    loaded = storage.load_existing()
    assert len(loaded) == 2
    assert doc1.doc_id in loaded
    assert doc2.doc_id in loaded

    # Verify content survived the round-trip.
    assert loaded[doc1.doc_id].title == doc1.title
    assert loaded[doc1.doc_id].word_count == doc1.word_count
    assert loaded[doc1.doc_id].url == doc1.url
