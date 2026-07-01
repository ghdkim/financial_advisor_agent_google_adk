"""Fundamental-analysis sub-agent."""

from __future__ import annotations

import math
import os
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf
from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm

MODEL = LiteLlm(model=os.getenv("FINANCIAL_AGENT_MODEL", "openai/gpt-5.4-mini"))


def _ticker(value: str) -> str:
    ticker = (value or "").strip().upper()
    if not ticker or len(ticker) > 20:
        raise ValueError("Provide a valid ticker symbol.")
    return ticker


def _value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return None if math.isnan(float(value)) else float(value)
    return value


def _row(frame: pd.DataFrame, *names: str) -> pd.Series:
    for name in names:
        if name in frame.index:
            return pd.to_numeric(frame.loc[name], errors="coerce")
    return pd.Series(dtype=float)


def _series_payload(series: pd.Series) -> list[dict[str, Any]]:
    return [
        {"period": pd.Timestamp(index).date().isoformat(), "value": _value(value)}
        for index, value in series.dropna().items()
    ]


def get_financial_statements(ticker: str, frequency: str = "annual") -> dict[str, Any]:
    """Retrieve income statement, balance sheet, and cash-flow statements."""
    symbol = _ticker(ticker)
    quarterly = frequency.lower().startswith("q")
    try:
        stock = yf.Ticker(symbol)
        income = stock.quarterly_income_stmt if quarterly else stock.income_stmt
        balance = stock.quarterly_balance_sheet if quarterly else stock.balance_sheet
        cashflow = stock.quarterly_cashflow if quarterly else stock.cashflow
        if income.empty and balance.empty and cashflow.empty:
            return {"success": False, "ticker": symbol, "error": "No financial statements were returned."}
        return {
            "success": True,
            "ticker": symbol,
            "frequency": "quarterly" if quarterly else "annual",
            "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
            "income_statement": income.to_json(date_format="iso"),
            "balance_sheet": balance.to_json(date_format="iso"),
            "cash_flow": cashflow.to_json(date_format="iso"),
            "source": "Yahoo Finance via yfinance; reconcile material figures with issuer filings.",
        }
    except Exception as exc:
        return {"success": False, "ticker": symbol, "error": f"Statement retrieval failed: {type(exc).__name__}: {exc}"}


def calculate_fundamental_trends(ticker: str, frequency: str = "annual") -> dict[str, Any]:
    """Calculate revenue, margins, cash generation, leverage, and growth trends."""
    symbol = _ticker(ticker)
    quarterly = frequency.lower().startswith("q")
    try:
        stock = yf.Ticker(symbol)
        inc = stock.quarterly_income_stmt if quarterly else stock.income_stmt
        bal = stock.quarterly_balance_sheet if quarterly else stock.balance_sheet
        cf = stock.quarterly_cashflow if quarterly else stock.cashflow
        if inc.empty:
            return {"success": False, "ticker": symbol, "error": "Income statement is unavailable."}

        revenue = _row(inc, "Total Revenue", "Operating Revenue").sort_index()
        gross_profit = _row(inc, "Gross Profit").sort_index()
        operating_income = _row(inc, "Operating Income").sort_index()
        net_income = _row(inc, "Net Income", "Net Income Common Stockholders").sort_index()
        ebitda = _row(inc, "EBITDA", "Normalized EBITDA").sort_index()
        operating_cf = _row(cf, "Operating Cash Flow", "Total Cash From Operating Activities").sort_index()
        capex = _row(cf, "Capital Expenditure", "Capital Expenditures").sort_index()
        free_cf = _row(cf, "Free Cash Flow").sort_index()
        if free_cf.empty and not operating_cf.empty and not capex.empty:
            free_cf = operating_cf.add(capex, fill_value=np.nan)
        cash = _row(bal, "Cash Cash Equivalents And Short Term Investments", "Cash And Cash Equivalents").sort_index()
        debt = _row(bal, "Total Debt").sort_index()
        equity = _row(bal, "Stockholders Equity", "Total Stockholder Equity").sort_index()
        current_assets = _row(bal, "Current Assets", "Total Current Assets").sort_index()
        current_liabilities = _row(bal, "Current Liabilities", "Total Current Liabilities").sort_index()

        latest_period = revenue.index[-1] if not revenue.empty else inc.columns[0]
        latest_revenue = revenue.get(latest_period, np.nan)

        def latest_ratio(numerator: pd.Series, denominator: pd.Series) -> float | None:
            joined = pd.concat([numerator.rename("n"), denominator.rename("d")], axis=1).dropna()
            if joined.empty or joined.iloc[-1]["d"] == 0:
                return None
            return _value(joined.iloc[-1]["n"] / joined.iloc[-1]["d"])

        growth = revenue.pct_change().replace([np.inf, -np.inf], np.nan)
        fcf_margin = latest_ratio(free_cf, revenue)
        return {
            "success": True,
            "ticker": symbol,
            "frequency": "quarterly" if quarterly else "annual",
            "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
            "latest_reported_period": pd.Timestamp(latest_period).date().isoformat(),
            "latest_revenue": _value(latest_revenue),
            "latest_revenue_growth": _value(growth.iloc[-1]) if not growth.empty else None,
            "gross_margin": latest_ratio(gross_profit, revenue),
            "operating_margin": latest_ratio(operating_income, revenue),
            "net_margin": latest_ratio(net_income, revenue),
            "ebitda_margin": latest_ratio(ebitda, revenue),
            "free_cash_flow_margin": fcf_margin,
            "cash_to_debt": latest_ratio(cash, debt),
            "debt_to_equity": latest_ratio(debt, equity),
            "current_ratio": latest_ratio(current_assets, current_liabilities),
            "revenue_history": _series_payload(revenue),
            "net_income_history": _series_payload(net_income),
            "operating_cash_flow_history": _series_payload(operating_cf),
            "free_cash_flow_history": _series_payload(free_cf),
            "analysis_notes": [
                "Growth rates are sequential for quarterly data and year-over-year only for annual data.",
                "Accounting line-item availability varies by issuer and sector.",
                "Banks, insurers, REITs, and pre-revenue companies require sector-specific interpretation.",
            ],
        }
    except Exception as exc:
        return {"success": False, "ticker": symbol, "error": f"Fundamental calculation failed: {type(exc).__name__}: {exc}"}


def get_earnings_and_estimates(ticker: str) -> dict[str, Any]:
    """Retrieve earnings dates, surprises, growth estimates, and recommendation summaries."""
    symbol = _ticker(ticker)
    try:
        stock = yf.Ticker(symbol)
        calendar = stock.calendar or {}
        earnings_dates = stock.get_earnings_dates(limit=8)
        growth_estimates = stock.growth_estimates
        recommendations = stock.recommendations_summary
        return {
            "success": True,
            "ticker": symbol,
            "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
            "calendar": calendar,
            "earnings_dates": earnings_dates.to_json(date_format="iso") if earnings_dates is not None else None,
            "growth_estimates": growth_estimates.to_json(date_format="iso") if growth_estimates is not None else None,
            "recommendations_summary": recommendations.to_json(date_format="iso") if recommendations is not None else None,
            "warning": "Consensus estimates and recommendations can be stale, incomplete, or revised without notice.",
        }
    except Exception as exc:
        return {"success": False, "ticker": symbol, "error": f"Estimate retrieval failed: {type(exc).__name__}: {exc}"}


financial_analyst = Agent(
    name="FinancialAnalyst",
    model=MODEL,
    description="Analyzes financial statements, earnings quality, balance-sheet risk, and valuation context.",
    instruction="""
You are the fundamental-analysis specialist.

For a standard company review:
1. Call calculate_fundamental_trends using annual data.
2. Call it again with quarterly data when recent inflection matters.
3. Call get_earnings_and_estimates for earnings timing and expectation risk.
4. Use get_financial_statements only when detailed line-item inspection is needed.

Evaluate revenue durability, margins, free cash flow, capital intensity, leverage, liquidity,
dilution/buybacks, cyclicality, earnings quality, and valuation. Identify which conclusions are
facts, calculations, estimates, or assumptions. Compare reported periods correctly and do not
call sequential quarterly growth year-over-year growth. Flag sector-specific accounting limits.
Never invent values and never issue the parent agent's final trade decision.
""",
    tools=[get_financial_statements, calculate_fundamental_trends, get_earnings_and_estimates],
    output_key="financial_analyst_result",
)
