"""Data models shared across crawler, parser, and storage layers."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class CrawlTask:
    """Single URL scheduled for crawling."""

    url: str
    depth: int
    parent_url: str | None = None


@dataclass(slots=True)
class AIDocument:
    """AI-ready document object emitted by the pipeline."""

    doc_id: str
    source: str
    url: str
    title: str
    body_text: str
    fetched_at: str
    word_count: int
    char_count: int
    language: str | None = None
    content_type: str | None = None
    reading_time_minutes: int | None = None
    is_mostly_code: bool | None = None
    quality_signals: dict[str, float] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    raw_metadata: dict[str, Any] = field(default_factory=dict)
    links_out_internal: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dictionary representation."""

        return asdict(self)
