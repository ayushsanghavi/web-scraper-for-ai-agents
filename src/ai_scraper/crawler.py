"""Crawl orchestrator — BFS crawl loop

    Seed URL → Queue → [Fetch → Parse → Enrich → Collect] → Storage
                  ↑         ↓
                  ← Filter ← discovered links

The Crawler never touches the network, HTML, or JSON directly — it delegates
to Fetcher, Parser, Enricher, Filter, and Storage respectively.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from datetime import datetime, timezone

from ai_scraper.config import CrawlConfig
from ai_scraper.enricher import DocumentEnricher
from ai_scraper.fetcher import PageFetcher
from ai_scraper.filters import URLFilter
from ai_scraper.models import AIDocument, CrawlTask
from ai_scraper.parser import create_parser
from ai_scraper.storage import JSONLStorage
from ai_scraper.utils import normalize_url, setup_logging

logger = logging.getLogger("ai_scraper")


class Crawler:
    """Breadth-first crawling.

    Coordinates fetching, parsing, enrichment, filtering, and storage.
    A single call to ``run()`` executes the full pipeline and returns
    the collected documents.
    """

    def __init__(self, config: CrawlConfig) -> None:
        self._config = config

        self._fetcher = PageFetcher(config)
        self._parser = create_parser("beautifulsoup", config)
        self._enricher = DocumentEnricher()
        self._filter = URLFilter(config)
        self._storage = JSONLStorage(config.output_path)

    def run(self) -> list[AIDocument]:
        """Execute the crawl and return collected documents.
            1/ Load existing seen documents
            2/ BFS the queue
            3/ Crawl every obj of the queue(i.e URL)
                a/ Fetch
                b/ Parse
                c/ Enrich
                d/ Filter
                3/ Storage"""

        setup_logging()

        documents = self._storage.load_existing()
        for doc_id, doc in documents.items():
            self._filter.mark_seen(doc.url)
        logger.info(
            "Resumed with %d existing documents (%d URLs marked seen)",
            len(documents), self._filter.seen_count,
        )

        seed = normalize_url(self._config.start_url)
        queue: deque[CrawlTask] = deque()

        if self._filter.should_crawl(seed):
            queue.append(CrawlTask(url=seed, depth=0))

        pages_kept = len(documents)
        pages_fetched = 0
        pages_failed = 0

        with self._fetcher:
            while queue and pages_kept < self._config.max_pages:
                task = queue.popleft()

                if task.depth > self._config.max_depth:
                    continue

                # Throttle.
                if pages_fetched > 0:
                    time.sleep(self._config.delay_seconds)

                fetch_result = self._fetcher.fetch(task.url)
                pages_fetched += 1

                if not fetch_result.success:
                    pages_failed += 1
                    logger.warning(
                        "Fetch failed [%s]: %s", fetch_result.error, task.url
                    )
                    continue

                parse_result = self._parser.parse(fetch_result.html, fetch_result.final_url)

                if parse_result is None:
                    logger.debug("Parser returned nothing for %s", task.url)
                    continue

                fetched_at = datetime.now(timezone.utc)
                doc = self._enricher.enrich(
                    parse_result,
                    url=normalize_url(fetch_result.final_url),
                    fetched_at=fetched_at,
                )

                # Store (keyed by doc_id so re-crawled pages overwrite).
                documents[doc.doc_id] = doc
                pages_kept = len(documents)
                logger.info(
                    "[%d/%d] %s  (%d words, %s)",
                    pages_kept, self._config.max_pages,
                    doc.title or "(untitled)",
                    doc.word_count,
                    doc.content_type,
                )

                #  Discover links , filter, enqueue...
                if task.depth < self._config.max_depth:
                    for link in parse_result.links_internal:
                        if self._filter.should_crawl(link):
                            queue.append(CrawlTask(
                                url=link,
                                depth=task.depth + 1,
                                parent_url=task.url,
                            ))

        # Save
        doc_list = list(documents.values())
        self._storage.save(doc_list)

        logger.info(
            "Crawl complete: %d pages fetched, %d failed, %d documents saved",
            pages_fetched, pages_failed, len(doc_list),
        )

        return doc_list
