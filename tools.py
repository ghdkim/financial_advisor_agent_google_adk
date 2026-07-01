"""Shared web-research tools for the financial advisor agent."""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv
from firecrawl import FirecrawlApp, ScrapeOptions

load_dotenv()

_MAX_RESULTS = 8
_MAX_MARKDOWN_CHARS = 12_000


def _clean_markdown(value: str | None) -> str:
    """Normalize scraped markdown while preserving readable paragraph breaks."""
    text = value or ""
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()[:_MAX_MARKDOWN_CHARS]


def web_search_tool(query: str, limit: int = 6) -> dict[str, Any]:
    """Search and scrape current web sources with Firecrawl.

    Args:
        query: A precise finance/news query. Include the ticker, company name,
            topic, and recency terms when relevant.
        limit: Number of results to request, from 1 through 8.

    Returns:
        A structured response containing retrieval time, source titles, URLs,
        descriptions, publication dates when available, and cleaned markdown.
    """
    api_key = os.getenv("FIRECRAWL_API_KEY")
    if not api_key:
        return {
            "success": False,
            "error": "FIRECRAWL_API_KEY is not configured.",
            "query": query,
        }

    query = (query or "").strip()
    if not query:
        return {"success": False, "error": "Query cannot be empty."}

    safe_limit = max(1, min(int(limit), _MAX_RESULTS))

    try:
        app = FirecrawlApp(api_key=api_key)
        response = app.search(
            query=query,
            limit=safe_limit,
            scrape_options=ScrapeOptions(formats=["markdown"]),
        )

        if not getattr(response, "success", False):
            return {
                "success": False,
                "error": "Firecrawl search did not complete successfully.",
                "query": query,
            }

        sources: list[dict[str, Any]] = []
        for item in getattr(response, "data", []) or []:
            if hasattr(item, "model_dump"):
                item = item.model_dump()
            elif not isinstance(item, dict):
                item = vars(item)

            metadata = item.get("metadata") or {}
            sources.append(
                {
                    "title": item.get("title") or metadata.get("title") or "Untitled",
                    "url": item.get("url") or metadata.get("sourceURL"),
                    "description": item.get("description") or metadata.get("description"),
                    "published_date": (
                        item.get("publishedDate")
                        or item.get("published_date")
                        or metadata.get("publishedDate")
                    ),
                    "markdown": _clean_markdown(item.get("markdown")),
                }
            )

        return {
            "success": True,
            "query": query,
            "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
            "result_count": len(sources),
            "sources": sources,
            "warning": (
                "Search results may contain duplicated, syndicated, stale, or incorrect "
                "claims. Verify market-moving facts with primary filings or issuer releases."
            ),
        }
    except Exception as exc:  # tool boundary: return errors to the agent
        return {
            "success": False,
            "query": query,
            "error": f"Firecrawl search failed: {type(exc).__name__}: {exc}",
        }
