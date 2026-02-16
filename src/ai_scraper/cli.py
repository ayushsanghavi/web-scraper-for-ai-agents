"""CLI entrypoint for the scraper tool."""

from __future__ import annotations

import argparse

from ai_scraper.config import CrawlConfig, DEFAULT_USER_AGENT


def build_parser() -> argparse.ArgumentParser:
    """Create argument parser for the `scrape_site` command."""

    parser = argparse.ArgumentParser(
        prog="scrape_site",
        description="Crawl a public site and produce AI-ready JSONL documents.",
    )
    parser.add_argument("--start-url", required=True, help="Seed URL to start crawling from")
    parser.add_argument("--output", required=True, help="Output JSONL file path")
    parser.add_argument("--max-pages", type=int, default=100, help="Maximum number of pages to keep")
    parser.add_argument("--max-depth", type=int, default=2, help="Maximum crawl depth from seed URL")
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=0.5,
        help="Delay between requests to throttle crawling",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="HTTP request timeout in seconds",
    )
    parser.add_argument(
        "--user-agent",
        default=DEFAULT_USER_AGENT,
        help="User-Agent header used for requests",
    )
    parser.add_argument(
        "--allowed-path-prefix",
        default=None,
        help="Optional path prefix filter (example: /3/tutorial/)",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=2,
        help="Maximum retries for transient HTTP failures",
    )
    parser.add_argument(
        "--retry-backoff-seconds",
        type=float,
        default=0.5,
        help="Backoff multiplier between retries",
    )
    parser.add_argument(
        "--parser",
        dest="parser_backend",
        choices=["beautifulsoup", "trafilatura"],
        default="beautifulsoup",
        help="Content extraction backend: 'beautifulsoup' (heuristic) or 'trafilatura' (ML-based)",
    )
    return parser


def run_pipeline(config: CrawlConfig) -> int:
    """Run the full crawl pipeline."""

    from ai_scraper.crawler import Crawler

    try:
        crawler = Crawler(config)
        documents = crawler.run()
        print(f"Done — {len(documents)} documents saved to {config.output_path}")
        return 0
    except KeyboardInterrupt:
        print("\nCrawl interrupted by user.")
        return 130
    except Exception as exc:
        print(f"Fatal error: {exc}")
        return 1


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = CrawlConfig.from_namespace(args)
    return run_pipeline(config)


if __name__ == "__main__":
    raise SystemExit(main())
