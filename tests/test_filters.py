"""Tests for URL filtering."""

from ai_scraper.filters import URLFilter


def test_filter_accepts_good_urls_and_rejects_bad_ones(sample_config):
    """Filter should accept valid content URLs and reject duplicates,
    non-HTML extensions, and non-content patterns in a single pass."""

    url_filter = URLFilter(sample_config)

    # Good URL — accepted.
    assert url_filter.should_crawl("https://example.com/article/intro") is True

    # Duplicate — rejected.
    assert url_filter.should_crawl("https://example.com/article/intro") is False

    # Non-HTML extensions — rejected.
    assert url_filter.should_crawl("https://example.com/file.pdf") is False
    assert url_filter.should_crawl("https://example.com/image.png") is False

    # Non-content patterns — rejected.
    assert url_filter.should_crawl("https://example.com/login") is False
    assert url_filter.should_crawl("https://example.com/admin/dashboard") is False

    # Another good URL — accepted.
    assert url_filter.should_crawl("https://example.com/blog/post-1") is True


def test_filter_respects_path_prefix():
    """When allowed_path_prefix is set, only matching URLs pass."""

    from ai_scraper.config import CrawlConfig

    config = CrawlConfig(
        start_url="https://example.com/docs/",
        output_path="/tmp/test.jsonl",
        allowed_path_prefix="/docs/",
    )
    url_filter = URLFilter(config)

    assert url_filter.should_crawl("https://example.com/docs/getting-started") is True
    assert url_filter.should_crawl("https://example.com/blog/post-1") is False
