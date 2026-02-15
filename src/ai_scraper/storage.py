"""JSONL storage layer — writes AIDocument obj to disk.

Handles serialization, idempotency and atomic writes.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path

from ai_scraper.models import AIDocument

logger = logging.getLogger("ai_scraper")


class JSONLStorage:
    """Read and write AIDocument collections as newline-delimited JSON.

    Typical lifecycle during a crawl::

        storage = JSONLStorage("output/collection.jsonl")
        existing = storage.load_existing()
        storage.save(all_documents)
    """

    def __init__(self, output_path: str) -> None:
        self._path = Path(output_path)

    def load_existing(self) -> dict[str, AIDocument]:
        """Load a previous output file and return documents keyed by doc_id.
        """

        if not self._path.exists():
            return {}

        documents: dict[str, AIDocument] = {}
        skipped = 0

        with open(self._path, "r", encoding="utf-8") as fh:
            for line_num, line in enumerate(fh, start=1):
                line = line.strip()
                if not line:
                    continue

                try:
                    data = json.loads(line)
                    doc = self._dict_to_document(data)
                    documents[doc.doc_id] = doc
                except (json.JSONDecodeError, KeyError, TypeError) as exc:
                    skipped += 1
                    logger.warning(
                        "Skipped malformed line %d in %s: %s", line_num, self._path, exc
                    )

        if skipped:
            logger.warning(
                "Loaded %d documents from %s (%d lines skipped)",
                len(documents), self._path, skipped,
            )
        else:
            logger.info("Loaded %d existing documents from %s", len(documents), self._path)

        return documents

    def save(self, documents: list[AIDocument]) -> int:
        """Write documents to the output file atomically.
        Returns the number of documents written.
        """

        if not documents:
            logger.info("No documents to write")
            return 0

        # Ensure the parent directory exists.
        self._path.parent.mkdir(parents=True, exist_ok=True)

        # Write to a temp file in the same directory
        fd, tmp_path = tempfile.mkstemp(
            dir=self._path.parent,
            prefix=".tmp_",
            suffix=".jsonl",
        )

        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                for doc in documents:
                    line = json.dumps(doc.to_dict(), ensure_ascii=False, sort_keys=False)
                    fh.write(line + "\n")

            # Atomic rename — replaces the old file in one operation.
            os.replace(tmp_path, self._path)

        except Exception:
            # Clean up the temp file if anything goes wrong.
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

        logger.info("Wrote %d documents to %s", len(documents), self._path)
        return len(documents)

    @staticmethod
    def _dict_to_document(data: dict) -> AIDocument:
        """Reconstruct an AIDocument from a parsed JSON dictionary.
        """

        return AIDocument(
            doc_id=data["doc_id"],
            source=data["source"],
            url=data["url"],
            title=data["title"],
            body_text=data["body_text"],
            fetched_at=data["fetched_at"],
            word_count=data["word_count"],
            char_count=data["char_count"],
            language=data.get("language"),
            content_type=data.get("content_type"),
            reading_time_minutes=data.get("reading_time_minutes"),
            is_mostly_code=data.get("is_mostly_code"),
            quality_signals=data.get("quality_signals", {}),
            tags=data.get("tags", []),
            raw_metadata=data.get("raw_metadata", {}),
            links_out_internal=data.get("links_out_internal", []),
        )
