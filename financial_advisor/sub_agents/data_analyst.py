"""Market-data and technical-analysis sub-agent."""

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
_VALID_PERIODS = {"5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max"}


def _ticker(value: str) -> str:
    ticker = (value or "").strip().upper()
    if not ticker or len(ticker) > 20:
        raise ValueError("Provide a valid ticker symbol.")
    return ticker


def _json_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return None if math.isnan(float(value)) else float(value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value


def get_company_snapshot(ticker: str) -> dict[str, Any]:
    """Return company identity, quote metadata, valuation, and earnings context."""
    symbol = _ticker(ticker)
    try:
        stock = yf.Ticker(symbol)
        info = stock.info or {}
        fast = dict(stock.fast_info or {})
        quote_price = fast.get("last_price") or info.get("currentPrice") or info.get("regularMarketPrice")
        return {
            "success": True,
            "ticker": symbol,
            "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
            "company_name": info.get("longName") or info.get("shortName"),
            "quote_type": info.get("quoteType"),
            "exchange": info.get("exchange"),
            "currency": info.get("currency") or fast.get("currency"),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "country": info.get("country"),
            "current_price": _json_value(quote_price),
            "market_cap": _json_value(info.get("marketCap") or fast.get("market_cap")),
            "enterprise_value": _json_value(info.get("enterpriseValue")),
            "trailing_pe": _json_value(info.get("trailingPE")),
            "forward_pe": _json_value(info.get("forwardPE")),
            "price_to_sales": _json_value(info.get("priceToSalesTrailing12Months")),
            "price_to_book": _json_value(info.get("priceToBook")),
            "enterprise_to_ebitda": _json_value(info.get("enterpriseToEbitda")),
            "beta": _json_value(info.get("beta")),
            "dividend_yield": _json_value(info.get("dividendYield")),
            "fifty_two_week_low": _json_value(info.get("fiftyTwoWeekLow") or fast.get("year_low")),
            "fifty_two_week_high": _json_value(info.get("fiftyTwoWeekHigh") or fast.get("year_high")),
            "average_volume_10d": _json_value(info.get("averageDailyVolume10Day")),
            "analyst_target_mean": _json_value(info.get("targetMeanPrice")),
            "analyst_target_low": _json_value(info.get("targetLowPrice")),
            "analyst_target_high": _json_value(info.get("targetHighPrice")),
            "analyst_count": _json_value(info.get("numberOfAnalystOpinions")),
            "next_earnings_hint": info.get("earningsTimestampStart") or info.get("earningsTimestamp"),
            "source": "Yahoo Finance via yfinance; values may be delayed or incomplete.",
        }
    except Exception as exc:
        return {"success": False, "ticker": symbol, "error": f"Snapshot failed: {type(exc).__name__}: {exc}"}


def get_price_and_technical_analysis(ticker: str, period: str = "1y") -> dict[str, Any]:
    """Return historical price data plus reproducible trend, momentum, and risk metrics."""
    symbol = _ticker(ticker)
    selected_period = period if period in _VALID_PERIODS else "1y"
    try:
        history = yf.Ticker(symbol).history(period=selected_period, interval="1d", auto_adjust=True)
        if history.empty or "Close" not in history:
            return {"success": False, "ticker": symbol, "error": "No usable price history was returned."}

        close = history["Close"].dropna()
        volume = history.get("Volume", pd.Series(index=history.index, dtype=float)).fillna(0)
        returns = close.pct_change().dropna()

        delta = close.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9, adjust=False).mean()

        running_max = close.cummax()
        drawdown = close / running_max - 1
        annualized_volatility = returns.std() * np.sqrt(252) if len(returns) > 1 else np.nan

        def pct_change(days: int) -> float | None:
            return _json_value(close.iloc[-1] / close.iloc[-days - 1] - 1) if len(close) > days else None

        rows = history.tail(90).reset_index()
        date_col = rows.columns[0]
        price_rows = [
            {
                "date": _json_value(row[date_col]),
                "open": _json_value(row.get("Open")),
                "high": _json_value(row.get("High")),
                "low": _json_value(row.get("Low")),
                "close": _json_value(row.get("Close")),
                "volume": _json_value(row.get("Volume")),
            }
            for _, row in rows.iterrows()
        ]

        return {
            "success": True,
            "ticker": symbol,
            "period": selected_period,
            "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
            "last_market_date": close.index[-1].isoformat(),
            "last_close": _json_value(close.iloc[-1]),
            "return_5d": pct_change(5),
            "return_21d": pct_change(21),
            "return_63d": pct_change(63),
            "return_252d": pct_change(252),
            "sma_20": _json_value(close.rolling(20).mean().iloc[-1]),
            "sma_50": _json_value(close.rolling(50).mean().iloc[-1]),
            "sma_200": _json_value(close.rolling(200).mean().iloc[-1]),
            "rsi_14": _json_value(rsi.iloc[-1]),
            "macd": _json_value(macd.iloc[-1]),
            "macd_signal": _json_value(signal.iloc[-1]),
            "annualized_volatility": _json_value(annualized_volatility),
            "max_drawdown_for_period": _json_value(drawdown.min()),
            "average_volume_20d": _json_value(volume.tail(20).mean()),
            "recent_ohlcv": price_rows,
            "source": "Yahoo Finance via yfinance; daily data may be delayed and is not an execution feed.",
        }
    except Exception as exc:
        return {"success": False, "ticker": symbol, "error": f"Technical analysis failed: {type(exc).__name__}: {exc}"}


def compare_with_benchmark(ticker: str, benchmark: str = "SPY", period: str = "1y") -> dict[str, Any]:
    """Compare total return, beta, correlation, and risk-adjusted performance to a benchmark."""
    symbol, bench = _ticker(ticker), _ticker(benchmark)
    selected_period = period if period in _VALID_PERIODS else "1y"
    try:
        prices = yf.download([symbol, bench], period=selected_period, auto_adjust=True, progress=False)["Close"]
        prices = prices.dropna()
        if prices.empty or symbol not in prices or bench not in prices:
            return {"success": False, "ticker": symbol, "benchmark": bench, "error": "Insufficient overlapping price data."}
        rets = prices.pct_change().dropna()
        total = prices.iloc[-1] / prices.iloc[0] - 1
        covariance = rets[symbol].cov(rets[bench])
        variance = rets[bench].var()
        beta = covariance / variance if variance else np.nan
        active = rets[symbol] - rets[bench]
        tracking_error = active.std() * np.sqrt(252)
        information_ratio = active.mean() * 252 / tracking_error if tracking_error else np.nan
        return {
            "success": True,
            "ticker": symbol,
            "benchmark": bench,
            "period": selected_period,
            "ticker_total_return": _json_value(total[symbol]),
            "benchmark_total_return": _json_value(total[bench]),
            "excess_return": _json_value(total[symbol] - total[bench]),
            "beta_to_benchmark": _json_value(beta),
            "daily_return_correlation": _json_value(rets[symbol].corr(rets[bench])),
            "annualized_tracking_error": _json_value(tracking_error),
            "information_ratio": _json_value(information_ratio),
        }
    except Exception as exc:
        return {"success": False, "ticker": symbol, "benchmark": bench, "error": f"Benchmark comparison failed: {type(exc).__name__}: {exc}"}


data_analyst = Agent(
    name="DataAnalyst",
    model=MODEL,
    description="Retrieves timestamped market data and computes reproducible technical and benchmark metrics.",
    instruction="""
You are the market-data specialist. Always call the relevant tools rather than relying on memory.

Required behavior:
- Confirm the ticker/company identity before interpreting metrics.
- For a normal equity review, call get_company_snapshot and get_price_and_technical_analysis.
- Use compare_with_benchmark when performance or relative attractiveness matters.
- State the retrieval timestamp and last market date.
- Distinguish price facts from interpretation.
- Flag missing fields, stale/delayed data, thin liquidity, extreme volatility, and corporate-action distortions.
- Never invent intraday quotes, support/resistance, or analyst targets.
- Do not issue the final BUY/HOLD/SELL decision; provide evidence to the parent agent.
""",
    tools=[get_company_snapshot, get_price_and_technical_analysis, compare_with_benchmark],
    output_key="data_analyst_result",
)
