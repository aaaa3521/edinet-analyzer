"""
Yahoo Finance クライアント
yfinance を使って株価・PER・PBR・EPS履歴を取得する
日本株は証券コードに ".T" サフィックスを付ける
"""

import yfinance as yf
import pandas as pd
from typing import Optional


def _ticker(securities_code: str) -> yf.Ticker:
    code = securities_code.strip()
    if not code.endswith(".T"):
        code = f"{code}.T"
    return yf.Ticker(code)


def get_stock_info(securities_code: str) -> dict:
    """
    株価・PER・PBR・時価総額・EPS等の基本情報を取得する
    取得できない項目はNone
    """
    t = _ticker(securities_code)
    try:
        info = t.info
    except Exception:
        info = {}

    return {
        "current_price": info.get("currentPrice") or info.get("regularMarketPrice"),
        "per": info.get("trailingPE"),
        "forward_per": info.get("forwardPE"),
        "pbr": info.get("priceToBook"),
        "market_cap": info.get("marketCap"),
        "eps": info.get("trailingEps"),
        "dividend_yield": info.get("dividendYield"),
        "52w_high": info.get("fiftyTwoWeekHigh"),
        "52w_low": info.get("fiftyTwoWeekLow"),
        "company_name": info.get("longName") or info.get("shortName", securities_code),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
    }


def get_price_history(
    securities_code: str,
    period: str = "2y",
    interval: str = "1mo",
) -> pd.DataFrame:
    """
    株価の時系列データを取得する
    period: 1mo, 3mo, 6mo, 1y, 2y, 5y
    interval: 1d, 1wk, 1mo
    返り値: DataFrame(index=Date, columns=[Open,High,Low,Close,Volume])
    """
    t = _ticker(securities_code)
    try:
        df = t.history(period=period, interval=interval)
        df.index = pd.to_datetime(df.index).tz_localize(None)
        return df[["Open", "High", "Low", "Close", "Volume"]]
    except Exception:
        return pd.DataFrame()


def get_earnings_history(securities_code: str) -> pd.DataFrame:
    """
    EPSの年次履歴を取得する
    返り値: DataFrame(index=Year, columns=[epsActual, epsEstimate, ...])
    """
    t = _ticker(securities_code)
    try:
        earnings = t.earnings_history
        if earnings is not None and not earnings.empty:
            return earnings
        # 代替: income_stmt の EPS 行
        income = t.financials
        if income is not None and not income.empty:
            eps_row = income[income.index.str.contains("EPS|Diluted", case=False, na=False)]
            if not eps_row.empty:
                return eps_row.T.rename(columns={eps_row.index[0]: "eps"})
    except Exception:
        pass
    return pd.DataFrame()


def get_income_history(securities_code: str) -> pd.DataFrame:
    """
    年次損益計算書の推移を取得する（最大4期分）
    返り値: DataFrame
        index   = 会計年度（datetime）
        columns = [売上高, 営業利益, 税引前利益, 当期純利益]
    経常利益はYahoo Financeに存在しないため税引前利益（Pretax Income）で近似する
    """
    t = _ticker(securities_code)
    try:
        df = t.income_stmt  # index=指標名, columns=決算日
        if df is None or df.empty:
            return pd.DataFrame()

        ROW_MAP = {
            "Total Revenue":    "売上高",
            "Operating Income": "営業利益",
            "Pretax Income":    "税引前利益(経常利益近似)",
            "Net Income":       "当期純利益",
        }
        rows = {jp: df.loc[en] for en, jp in ROW_MAP.items() if en in df.index}
        if not rows:
            return pd.DataFrame()

        result = pd.DataFrame(rows).T          # index=指標名, columns=決算日
        result = result.T                       # index=決算日, columns=指標名
        result.index = pd.to_datetime(result.index).tz_localize(None)
        result = result.sort_index()            # 古い順に並べ替え
        result = result.apply(pd.to_numeric, errors="coerce")
        return result

    except Exception:
        return pd.DataFrame()


def get_multi_stock_info(securities_codes: list[str]) -> dict[str, dict]:
    """複数証券コードの株価情報を一括取得する"""
    return {code: get_stock_info(code) for code in securities_codes}
