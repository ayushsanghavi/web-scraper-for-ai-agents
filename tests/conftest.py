import pytest

from ai_scraper.config import CrawlConfig
from ai_scraper.parser import ParseResult

@pytest.fixture
def sample_html():
    """HTML page with nav, main content, footer, and meta tags."""
    return """
    <html>
    <head>
        <title>Test Article — Example Site</title>
        <meta name="description" content="A test description.">
        <meta name="author" content="Test Author">
    </head>
    <body>
        <nav><a href="/home">Home</a></nav>
        <main>
            <h1>Test Article</h1>
            <p>This is the main body content of the article. It has enough
            text to be meaningful for testing extraction and enrichment.</p>
            <a href="/related">Related</a>
            <a href="https://external.com/nope">External</a>
        </main>
        <footer><p>Copyright 2026</p></footer>
    </body>
    </html>
    """

@pytest.fixture
def sample_config():
    return CrawlConfig(
        start_url="https://docs.com",
        output_path="/tmp/test_output.jsonl",
        max_pages=10,
        max_depth=2,
    )


@pytest.fixture
def sample_parse_result():
    """Typical ParseResult for enricher/storage testing."""
    return ParseResult(
        title="Test Document",
        body_text="This is a sufficiently long body text for testing. " * 20,
        links_internal=["https://example.com/page1", "https://example.com/page2"],
        meta={"description": "A test document", "author": "Tester"},
        code_text_length=0,
        html_length=5000,
    )
