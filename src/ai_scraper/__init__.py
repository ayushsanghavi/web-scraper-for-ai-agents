"""
ai_scraper
==================

A production-grade AI data collection pipeline that scrapes, cleans,
enriches, and outputs AI-ready document objects in JSONL format.

Architecture:
    CLI → Crawler → [Fetcher, Parser, Enricher, Filters] → Storage

Usage:
    scrape_site --start-url https://books.toscrape.com --max-pages 50
"""

# The version string is the single source of truth for the package version.
# It matches the version in pyproject.toml.
# Tools and other modules can import it: `from ai_scraper import __version__`
__version__ = "1.0.0"
