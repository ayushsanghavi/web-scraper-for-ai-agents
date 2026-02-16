#!/usr/bin/env python3
"""Analyze a scraped JSONL collection and print summary statistics.
Usage:
    python analytics/analyze_collection.py output/collection.jsonl --html
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import pandas as pd
    from tabulate import tabulate
except ImportError:
    print("Analytics dependencies not installed. Run: pip install '.[analytics]'")
    sys.exit(1)


# ── Helpers ──────────────────────────────────────────────────────────────────

def load_jsonl(path: str) -> pd.DataFrame:
    """Load a JSONL file into a DataFrame."""

    records = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))

    if not records:
        print(f"No documents found in {path}")
        sys.exit(1)

    return pd.DataFrame(records)


def section(title: str) -> None:
    """Print a section header."""
    width = 60
    print(f"\n{'=' * width}")
    print(f"  {title}")
    print(f"{'=' * width}")


# ── Analysis Sections ────────────────────────────────────────────────────────

def overview(df: pd.DataFrame) -> None:
    """High-level collection stats."""

    section("COLLECTION OVERVIEW")
    print("  Sanity-check that the crawl produced expected volume.\n")

    stats = {
        "Total documents": len(df),
        "Unique sources": df["source"].nunique(),
        "Date range": f"{df['fetched_at'].min()} → {df['fetched_at'].max()}",
        "Total words": f"{df['word_count'].sum():,}",
        "Total characters": f"{df['char_count'].sum():,}",
    }

    for label, value in stats.items():
        print(f"  {label:<25} {value}")


def content_type_breakdown(df: pd.DataFrame) -> None:
    """Distribution of heuristic content types."""

    section("CONTENT TYPE BREAKDOWN")
    print("  Heuristic page classification (article, reference, product, profile, listing, faq, other).\n")

    type_table = (
        df["content_type"]
        .fillna("null")
        .value_counts()
        .reset_index()
    )
    type_table.columns = ["Content Type", "Count"]
    type_table["% of Total"] = (type_table["Count"] / len(df) * 100).round(1)

    # Add average word count per type.
    avg_wc = df.groupby("content_type")["word_count"].mean().round(0).to_dict()
    type_table["Avg Words"] = type_table["Content Type"].map(avg_wc).fillna(0).astype(int)

    print(tabulate(type_table, headers="keys", tablefmt="simple", showindex=False))


def language_distribution(df: pd.DataFrame) -> None:
    """Language breakdown."""

    section("LANGUAGE DISTRIBUTION")
    print("  Route docs to language-matched embeddings or filter non-target languages.\n")

    lang_table = (
        df["language"]
        .fillna("undetected")
        .value_counts()
        .reset_index()
    )
    lang_table.columns = ["Language", "Count"]
    lang_table["% of Total"] = (lang_table["Count"] / len(df) * 100).round(1)

    print(tabulate(lang_table, headers="keys", tablefmt="simple", showindex=False))


def ai_readiness_score(df: pd.DataFrame) -> None:
    """Estimate what percentage of the collection is AI-ready.

    A document is considered "AI-ready" if it has:
    - At least 50 words (not too thin)
    - A detected language (not garbage text)
    - A text-to-html ratio above 0.03 (clean extraction)
    """

    section("AI READINESS ESTIMATE")
    print("  Docs with 50+ words, detected language, and text_to_html_ratio > 0.03.")
    print("  This is the usable portion for downstream AI pipelines.\n")

    ratio = df.get("text_to_html_ratio", pd.Series([0] * len(df)))

    ready = (
        (df["word_count"] >= 50)
        & (df["language"].notna())
        & (ratio > 0.03)
    )

    ready_count = ready.sum()
    total = len(df)

    print(f"  AI-ready documents: {ready_count} / {total} ({ready_count / total * 100:.1f}%)")
    print(f"  Filtered out:       {total - ready_count} (too short, no language, or low extraction ratio)")


# ── HTML Report Generator ───────────────────────────────────────────────────

COLORS = ["#2563eb", "#7c3aed", "#059669", "#d97706", "#dc2626", "#0891b2", "#4f46e5", "#be185d"]


def _html_escape(text: str) -> str:
    """Escape HTML special characters."""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _svg_donut(slices: list[tuple[str, float]], size: int = 180) -> str:
    """Generate an SVG donut chart. Each slice is (label, percentage 0-100)."""
    cx, cy, r = size // 2, size // 2, size // 2 - 20
    stroke_width = 30
    circumference = 2 * 3.14159 * r
    offset = 0
    paths = []
    legend_items = []

    for i, (label, pct) in enumerate(slices):
        if pct <= 0:
            continue
        color = COLORS[i % len(COLORS)]
        dash = circumference * pct / 100
        gap = circumference - dash
        paths.append(
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" '
            f'stroke="{color}" stroke-width="{stroke_width}" '
            f'stroke-dasharray="{dash:.1f} {gap:.1f}" '
            f'stroke-dashoffset="{-offset:.1f}" />'
        )
        offset += dash
        legend_items.append(
            f'<span style="display:inline-flex;align-items:center;margin-right:14px;">'
            f'<span style="width:10px;height:10px;border-radius:50%;background:{color};'
            f'display:inline-block;margin-right:5px;"></span>'
            f'{_html_escape(label)} ({pct:.1f}%)</span>'
        )

    svg = (
        f'<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}" '
        f'style="transform:rotate(-90deg);">'
        + "".join(paths)
        + "</svg>"
    )
    legend = '<div style="margin-top:10px;font-size:0.85rem;color:#555;">' + "".join(legend_items) + "</div>"
    return f'<div style="text-align:center;">{svg}{legend}</div>'


def _svg_bar_chart(items: list[tuple[str, float]], max_val: float | None = None,
                   color: str = "#2563eb", unit: str = "") -> str:
    """Generate horizontal bar chart as HTML with CSS bars."""
    if not items:
        return "<p>No data.</p>"
    if max_val is None:
        max_val = max(v for _, v in items) or 1
    rows = []
    for label, value in items:
        pct = (value / max_val * 100) if max_val else 0
        rows.append(
            f'<div style="display:flex;align-items:center;margin-bottom:6px;">'
            f'<div style="width:120px;font-size:0.85rem;color:#444;text-align:right;'
            f'padding-right:10px;flex-shrink:0;">{_html_escape(str(label))}</div>'
            f'<div style="flex:1;background:#e5e7eb;border-radius:4px;height:24px;overflow:hidden;">'
            f'<div style="width:{pct:.1f}%;background:{color};height:100%;border-radius:4px;'
            f'transition:width 0.3s;"></div></div>'
            f'<div style="width:70px;font-size:0.85rem;color:#666;padding-left:8px;">'
            f'{value:.0f}{unit}</div></div>'
        )
    return "".join(rows)


def _stat_card(label: str, value: str, color: str = "#2563eb") -> str:
    """Render a single stat card."""
    return (
        f'<div style="background:white;border-radius:10px;padding:20px 16px;text-align:center;'
        f'box-shadow:0 1px 3px rgba(0,0,0,.08);min-width:150px;">'
        f'<div style="font-size:1.8rem;font-weight:700;color:{color};">{_html_escape(str(value))}</div>'
        f'<div style="font-size:0.8rem;color:#888;margin-top:4px;">{_html_escape(label)}</div></div>'
    )


def _card(title: str, content: str, subtitle: str = "") -> str:
    """Wrap content in a dashboard card."""
    sub = (
        f'<p style="margin:0 0 16px 0;font-size:0.82rem;color:#94a3b8;line-height:1.4;">'
        f'{_html_escape(subtitle)}</p>'
    ) if subtitle else ""
    return (
        f'<div style="background:white;border-radius:10px;padding:24px;margin-bottom:20px;'
        f'box-shadow:0 1px 3px rgba(0,0,0,.08);">'
        f'<h2 style="margin:0 0 {"4px" if subtitle else "16px"} 0;font-size:1.1rem;color:#1e293b;">'
        f'{_html_escape(title)}</h2>'
        f'{sub}{content}</div>'
    )


def _html_table(headers: list[str], rows: list[list], highlight_col: int | None = None) -> str:
    """Render a simple HTML table."""
    th = "".join(
        f'<th style="padding:8px 12px;text-align:left;border-bottom:2px solid #e2e8f0;'
        f'font-size:0.8rem;color:#64748b;text-transform:uppercase;letter-spacing:0.05em;">'
        f'{_html_escape(h)}</th>' for h in headers
    )
    body_rows = []
    for row in rows:
        cells = []
        for j, cell in enumerate(row):
            weight = "font-weight:600;color:#2563eb;" if j == highlight_col else ""
            cells.append(
                f'<td style="padding:8px 12px;border-bottom:1px solid #f1f5f9;font-size:0.9rem;{weight}">'
                f'{_html_escape(str(cell))}</td>'
            )
        body_rows.append(f'<tr>{"".join(cells)}</tr>')
    return (
        f'<table style="width:100%;border-collapse:collapse;">'
        f'<thead><tr>{th}</tr></thead><tbody>{"".join(body_rows)}</tbody></table>'
    )


def _progress_bar(pct: float, label: str, color: str = "#059669") -> str:
    """Render a progress bar with label."""
    return (
        f'<div style="margin-bottom:8px;">'
        f'<div style="display:flex;justify-content:space-between;margin-bottom:4px;">'
        f'<span style="font-size:0.9rem;color:#444;">{_html_escape(label)}</span>'
        f'<span style="font-size:0.9rem;font-weight:600;color:{color};">{pct:.1f}%</span></div>'
        f'<div style="background:#e5e7eb;border-radius:6px;height:20px;overflow:hidden;">'
        f'<div style="width:{pct:.1f}%;background:{color};height:100%;border-radius:6px;'
        f'transition:width 0.3s;"></div></div></div>'
    )


def generate_html_report(df: pd.DataFrame, output_path: str, source_file: str) -> str:
    """Generate a self-contained HTML dashboard from the DataFrame."""

    total = len(df)
    source_name = df["source"].iloc[0] if len(df) > 0 else "unknown"
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # ── Overview stat cards ──
    overview_cards = (
        f'<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:14px;'
        f'margin-bottom:20px;">'
        + _stat_card("Total Documents", str(total))
        + _stat_card("Unique Sources", str(df["source"].nunique()), "#7c3aed")
        + _stat_card("Total Words", f'{df["word_count"].sum():,}', "#059669")
        + _stat_card("Total Characters", f'{df["char_count"].sum():,}', "#d97706")
        + _stat_card("Avg Words/Doc", f'{df["word_count"].mean():.0f}', "#dc2626")
        + "</div>"
    )

    # ── Content type donut + table ──
    type_counts = df["content_type"].fillna("null").value_counts()
    type_slices = [(str(ct), count / total * 100) for ct, count in type_counts.items()]
    avg_wc = df.groupby("content_type")["word_count"].mean().round(0).to_dict()
    type_table_rows = []
    for ct, count in type_counts.items():
        pct = count / total * 100
        avg = avg_wc.get(ct, 0)
        type_table_rows.append([str(ct), count, f"{pct:.1f}%", f"{avg:.0f}"])
    type_donut = _svg_donut(type_slices)
    type_tbl = _html_table(["Content Type", "Count", "% of Total", "Avg Words"], type_table_rows, highlight_col=1)
    ct_section = (
        f'<div style="display:grid;grid-template-columns:200px 1fr;gap:24px;align-items:start;">'
        f'{type_donut}{type_tbl}</div>'
    )

    # ── Language distribution donut + table ──
    lang_counts = df["language"].fillna("undetected").value_counts()
    lang_slices = [(str(lang), count / total * 100) for lang, count in lang_counts.items()]
    lang_table_rows = [[str(lang), count, f"{count / total * 100:.1f}%"] for lang, count in lang_counts.items()]
    lang_donut = _svg_donut(lang_slices, size=160)
    lang_tbl = _html_table(["Language", "Count", "% of Total"], lang_table_rows, highlight_col=1)
    lang_section = (
        f'<div style="display:grid;grid-template-columns:180px 1fr;gap:24px;align-items:start;">'
        f'{lang_donut}{lang_tbl}</div>'
    )

    # ── AI readiness ──
    ratio = df.get("text_to_html_ratio", pd.Series([0] * total))
    ready = (df["word_count"] >= 50) & (df["language"].notna()) & (ratio > 0.03)
    ready_count = ready.sum()
    ready_pct = ready_count / total * 100 if total else 0
    filtered = total - ready_count
    ai_section = (
        _progress_bar(ready_pct, f"AI-Ready: {ready_count} / {total} documents")
        + f'<p style="font-size:0.85rem;color:#888;margin-top:8px;">'
        f'Filtered out: {filtered} (too short, no language, or low extraction ratio)</p>'
    )

    # ── Assemble full HTML ──
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Collection Report — {_html_escape(source_name)}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
         background: #f1f5f9; color: #1e293b; line-height: 1.5; padding: 24px; }}
  .container {{ max-width: 960px; margin: 0 auto; }}
  h1 {{ font-size: 1.6rem; margin-bottom: 4px; }}
  .subtitle {{ font-size: 0.85rem; color: #94a3b8; margin-bottom: 24px; }}
</style>
</head>
<body>
<div class="container">
  <h1>Collection Analysis Report</h1>
  <p class="subtitle">Source: {_html_escape(source_file)} &middot; Generated: {generated_at}</p>

  {overview_cards}
  {_card("Content Type Breakdown", ct_section,
         "Heuristic classification: article, reference, product, profile, listing, faq, or other.")}
  {_card("Language Distribution", lang_section,
         "Detected language of each document. Route to language-matched embeddings or filter out non-target languages.")}
  {_card("AI Readiness Estimate", ai_section,
         "Documents passing: 50+ words, detected language, and text_to_html_ratio above 0.03. "
         "This is the usable portion of your collection for downstream AI pipelines.")}

  <p style="text-align:center;font-size:0.8rem;color:#94a3b8;margin-top:32px;">
    Generated by ai-scraper analytics &middot; {total} documents analyzed
  </p>
</div>
</body>
</html>"""

    Path(output_path).write_text(html, encoding="utf-8")
    return output_path


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python analytics/analyze_collection.py <path-to-jsonl> [--html]")
        sys.exit(1)

    # Parse args manually (keep it simple, no argparse needed for 2 args).
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}

    if not args:
        print("Usage: python analytics/analyze_collection.py <path-to-jsonl> [--html]")
        sys.exit(1)

    jsonl_path = args[0]
    want_html = "--html" in flags

    if not Path(jsonl_path).exists():
        print(f"File not found: {jsonl_path}")
        sys.exit(1)

    df = load_jsonl(jsonl_path)

    overview(df)
    content_type_breakdown(df)
    language_distribution(df)
    ai_readiness_score(df)

    print(f"\n{'=' * 60}")
    print(f"  Analysis complete. {len(df)} documents analyzed.")
    print(f"{'=' * 60}\n")

    if want_html:
        p = Path(jsonl_path)
        html_path = str(p.parent / f"{p.stem}_report.html")
        generate_html_report(df, html_path, source_file=p.name)
        print(f"  HTML report: {html_path}")
        print(f"  Open in browser: file://{Path(html_path).resolve()}\n")


if __name__ == "__main__":
    main()
