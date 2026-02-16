# Web Scraper for AI agents

##### Scrape, clean, and enrich web content into AI-ready documents (JSONL) for RAG, search, and training pipelines.

![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue) ![Sandbox](https://img.shields.io/badge/sandbox-books.toscrape.com-green)

---

## Quick Start

```bash
# Clone and setup
cd scraper
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,analytics]"

# Run the scraper using BeautifulSoup (to use trafilatura, add arg --parser trafilatura)
scrape_site \
  --start-url https://books.toscrape.com \
  --max-pages 50 \
  --max-depth 2 \
  --output output/collection.jsonl

# Run tests
pytest

# Run analytics
python analytics/analyze_collection.py output/collection.jsonl
```

## Docker setup

If you don't want to install Python or manage dependencies, run the scraper entirely inside a Docker container. Otherwise, skip this section and use the scraper [as a library](#using-as-a-library) in your own Python project.

```bash
docker build -t ai-scraper .
docker run --rm -v $(pwd)/output:/app/output ai-scraper \
  --start-url https://books.toscrape.com \
  --max-pages 50 \
  --output output/collection.jsonl
```

---

## CLI Options

| Options                 | Default | Description |
|-------------------------|---|---|
| `--start-url`           | *required* | Seed URL to begin crawling |
| `--output`              | *required* | Output JSONL file path |
| `--max-pages`           | 100 | Maximum documents to collect |
| `--max-depth`           | 2 | Maximum link-follow depth from seed |
| `--delay-seconds`       | 0.5 | Throttle delay between requests |
| `--timeout`             | 10.0 | HTTP request timeout (seconds) |
| `--allowed-path-prefix` | None | Only crawl URLs whose path starts with this prefix (e.g. `/docs/`) |
| `--allowed-path-regex`  | None | Only crawl URLs whose path matches this regex (e.g. `/blog/\d{4}/`) |
| `--max-retries`         | 2 | Retry count for transient HTTP failures |
| `--user-agent`          | `ai-scraper/1.0` | User-Agent header |
| `--parser`              | `beautifulsoup` | Content extraction backend: `beautifulsoup` or `trafilatura` |


## Analytics Report

Run `python analytics/analyze_collection.py output/collection.jsonl` (add `--html` for a visual dashboard). Each section in the report includes a description explaining what the metric measures and why it matters for AI workflows.

## Output Schema

Each line in the output JSONL file is a JSON object with these fields:

| Field | Type | Description |
|---|---|---|
| `doc_id` | string | Deterministic SHA-256 hash of URL — enables idempotent re-crawls |
| `source` | string | Domain name (e.g. `books.toscrape.com`) |
| `url` | string | Canonical page URL |
| `title` | string | Cleaned page title (site-name suffix stripped) |
| `body_text` | string | Main content text — no HTML, no nav/footer boilerplate |
| `fetched_at` | string | ISO 8601 UTC timestamp |
| `word_count` | int | Word count of body_text |
| `char_count` | int | Character count of body_text |
| `language` | string? | ISO 639-1 code (`en`, `fr`, etc.) or null if too short to detect |
| `content_type` | string | Heuristic classification: `article`, `reference`, `product`, `profile`, `listing`, `faq`, or `other` |
| `text_to_html_ratio` | float | Ratio of extracted text to raw HTML length — higher = cleaner extraction |
| `links_out_internal` | array | Internal links discovered on the page |

Formal JSON Schema: [`schema/document_schema.json`](schema/document_schema.json)

---

## Using as a Library

The scraper can be embedded directly into any Python project — no CLI needed. Install the package and import the components you need.

```bash
pip install -e /path/to/scraper
```

### Basic usage

```python
from ai_scraper.config import CrawlConfig
from ai_scraper.crawler import Crawler

config = CrawlConfig(
    start_url="https://example.com",
    output_path="output/example.jsonl",
    max_pages=50,
    parser_backend="trafilatura",  # or "beautifulsoup"
)
crawler = Crawler(config)
documents = crawler.run()  # returns list[AIDocument]

for doc in documents:
    print(doc.doc_id, doc.title, doc.word_count)
```

### Accessing document fields

Every document is an `AIDocument` dataclass with all enriched fields:

```python
doc = documents[0]

doc.doc_id              # "a1b2c3d4e5f6g7h8"
doc.url                 # "https://example.com/page"
doc.title               # "Page Title"
doc.body_text           # cleaned main content
doc.word_count          # 396
doc.language            # "en"
doc.content_type        # "article", "reference", "product", "profile", "listing", "faq", or "other"
doc.text_to_html_ratio  # 0.15 (higher = cleaner extraction)
doc.to_dict()           # JSON-serializable dict for downstream systems
```

---

## Possible Extensions (future scope)

- **Async fetching** — swap `requests` for `aiohttp` to fetch multiple pages concurrently while still respecting rate limits
- **Embedding generation** — compute vector embeddings at scrape time so documents are index-ready
- **Entity extraction** — pull out named entities (names, amounts, regulation numbers) via spaCy or an LLM
- **Summarization** — generate a short summary per document for search snippets
- **Distributed crawling** — use a message queue (Redis, SQS) as the crawl frontier for multi-worker parallelism
