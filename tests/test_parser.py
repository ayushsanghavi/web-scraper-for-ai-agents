"""Tests for content extraction."""

from ai_scraper.parser import BSoupParser


def test_parser_extracts_content_and_strips_boilerplate(sample_html):
    """Parser should extract title, body, internal links, and meta —
    while stripping nav/footer boilerplate."""

    parser = BSoupParser(seed_domain="example.com")
    result = parser.parse(sample_html, "https://example.com/article")

    assert result is not None

    # Title extracted and site suffix stripped.
    assert result.title == "Test Article"

    # Body has the real content, not boilerplate.
    assert "main body content" in result.body_text
    assert "Copyright" not in result.body_text

    # Only internal links kept; external link filtered out.
    assert any("example.com" in link for link in result.links_internal)
    assert not any("external.com" in link for link in result.links_internal)

    # Meta tags captured.
    assert result.meta["description"] == "A test description."
    assert result.meta["author"] == "Test Author"
