"""Root financial-advisor agent."""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone

from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools import ToolContext
from google.adk.tools.agent_tool import AgentTool
from google.genai import types

from .prompt import PROMPT
from .sub_agents.data_analyst import data_analyst
from .sub_agents.financial_analyst import financial_analyst
from .sub_agents.news_analyst import news_analyst

MODEL = LiteLlm(model=os.getenv("FINANCIAL_AGENT_MODEL", "openai/gpt-5.4-mini"))


def _safe_ticker(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "", (value or "").upper())
    return cleaned[:20] or "SECURITY"


async def save_advice_report(tool_context: ToolContext, summary: str, ticker: str) -> dict[str, object]:
    """Save the completed research report as a Markdown ADK artifact."""
    state = tool_context.state
    data_result = state.get("data_analyst_result", "Not available")
    financial_result = state.get("financial_analyst_result", "Not available")
    news_result = state.get("news_analyst_result", "Not available")
    generated_at = datetime.now(timezone.utc).isoformat()

    report = f"""# Investment Research Report: {_safe_ticker(ticker)}

**Generated (UTC):** {generated_at}

> This report is for research and educational purposes. It is not a guarantee, execution feed,
> fiduciary recommendation, or substitute for a licensed professional who understands the user's
> complete financial circumstances.

## Executive Summary

{summary.strip()}

## Market Data and Technical Analysis

{data_result}

## Fundamental Analysis

{financial_result}

## News, Catalysts, and Source Review

{news_result}

## Data Limitations

Yahoo Finance and scraped web content may be delayed, incomplete, revised, duplicated, or incorrect.
Material conclusions should be checked against issuer filings, investor-relations releases, regulators,
and a real-time broker/exchange feed before capital is committed.
"""
    state["report"] = report
    filename = f"{_safe_ticker(ticker)}_investment_research.md"
    artifact = types.Part(
        inline_data=types.Blob(mime_type="text/markdown", data=report.encode("utf-8"))
    )
    await tool_context.save_artifact(filename, artifact)
    return {"success": True, "filename": filename, "generated_at_utc": generated_at}


financial_advisor = Agent(
    name="FinancialAdvisor",
    description="Institutional-style equity research coordinator using market, fundamental, and current-news specialists.",
    instruction=PROMPT,
    model=MODEL,
    tools=[
        AgentTool(agent=data_analyst),
        AgentTool(agent=financial_analyst),
        AgentTool(agent=news_analyst),
        save_advice_report,
    ],
)

root_agent = financial_advisor
