"""
財務指標計算ロジック
EDINET財務データ + Yahoo Finance データから各種指標を計算する
"""

from __future__ import annotations
import pandas as pd
from typing import Optional


def _safe_div(numerator, denominator) -> Optional[float]:
    """ゼロ除算・None安全な除算"""
    try:
        if denominator and denominator != 0:
            return numerator / denominator
    except (TypeError, ZeroDivisionError):
        pass
    return None


def calc_profitability(financials: dict, prev_financials: Optional[dict] = None) -> dict:
    """
    収益性指標を計算する
    - 売上高成長率 (前期比較が必要)
    - 営業利益率
    - ROE = 純利益 / 自己資本
    - ROA = 純利益 / 総資産
    """
    net_sales = financials.get("net_sales")
    operating_income = financials.get("operating_income")
    net_income = financials.get("net_income")
    total_assets = financials.get("total_assets")
    equity = financials.get("equity")

    # 売上成長率
    sales_growth = None
    if prev_financials:
        prev_sales = prev_financials.get("net_sales")
        sales_growth = _safe_div(
            (net_sales or 0) - (prev_sales or 0), prev_sales
        )
        if sales_growth is not None:
            sales_growth *= 100  # パーセント表示

    operating_margin = _safe_div(operating_income, net_sales)
    if operating_margin is not None:
        operating_margin *= 100

    roe = _safe_div(net_income, equity)
    if roe is not None:
        roe *= 100

    roa = _safe_div(net_income, total_assets)
    if roa is not None:
        roa *= 100

    return {
        "sales_growth_pct": sales_growth,
        "operating_margin_pct": operating_margin,
        "roe_pct": roe,
        "roa_pct": roa,
    }


def calc_safety(financials: dict) -> dict:
    """
    安全性指標を計算する
    - 自己資本比率 = 自己資本 / 総資産
    - D/E レシオ = 有利子負債 / 自己資本
    """
    total_assets = financials.get("total_assets")
    equity = financials.get("equity")
    interest_bearing_debt = financials.get("interest_bearing_debt")

    equity_ratio = _safe_div(equity, total_assets)
    if equity_ratio is not None:
        equity_ratio *= 100

    de_ratio = _safe_div(interest_bearing_debt, equity)

    return {
        "equity_ratio_pct": equity_ratio,
        "de_ratio": de_ratio,
    }


def calc_valuation(stock_info: dict, financials: dict) -> dict:
    """
    バリュエーション指標を整理する
    Yahoo Finance から取得した値を使い、不足分は財務データで補完する
    """
    per = stock_info.get("per")
    forward_per = stock_info.get("forward_per")
    pbr = stock_info.get("pbr")
    eps = stock_info.get("eps")
    current_price = stock_info.get("current_price")
    market_cap = stock_info.get("market_cap")

    # EPS が Yahoo から取れない場合は財務データから算出
    if eps is None:
        net_income = financials.get("net_income")
        shares = financials.get("shares_outstanding")
        eps = _safe_div(net_income, shares)

    return {
        "per": per,
        "forward_per": forward_per,
        "pbr": pbr,
        "eps": eps,
        "current_price": current_price,
        "market_cap": market_cap,
        "dividend_yield_pct": (
            (stock_info.get("dividend_yield") or 0) * 100
            if stock_info.get("dividend_yield") is not None
            else None
        ),
    }


def build_summary_df(companies_data: dict[str, dict]) -> pd.DataFrame:
    """
    複数社の指標をまとめたサマリーDataFrameを生成する
    companies_data: {
        "7203": {
            "financials": {...},
            "stock_info": {...},
            "prev_financials": {...},  # optional
        },
        ...
    }
    """
    rows = []
    for code, data in companies_data.items():
        financials = data.get("financials", {})
        stock_info = data.get("stock_info", {})
        prev_financials = data.get("prev_financials")

        profitability = calc_profitability(financials, prev_financials)
        safety = calc_safety(financials)
        valuation = calc_valuation(stock_info, financials)

        row = {
            "証券コード": code,
            "会社名": stock_info.get("company_name", code),
            "株価": stock_info.get("current_price"),
            "時価総額": stock_info.get("market_cap"),
            # 収益性
            "売上高": financials.get("net_sales"),
            "営業利益": financials.get("operating_income"),
            "純利益": financials.get("net_income"),
            "売上成長率(%)": profitability.get("sales_growth_pct"),
            "営業利益率(%)": profitability.get("operating_margin_pct"),
            "ROE(%)": profitability.get("roe_pct"),
            "ROA(%)": profitability.get("roa_pct"),
            # 安全性
            "総資産": financials.get("total_assets"),
            "自己資本": financials.get("equity"),
            "有利子負債": financials.get("interest_bearing_debt"),
            "自己資本比率(%)": safety.get("equity_ratio_pct"),
            "D/Eレシオ": safety.get("de_ratio"),
            # バリュエーション
            "PER": valuation.get("per"),
            "PBR": valuation.get("pbr"),
            "EPS": valuation.get("eps"),
            "配当利回り(%)": valuation.get("dividend_yield_pct"),
        }
        rows.append(row)

    df = pd.DataFrame(rows).set_index("証券コード")
    # 数値列を明示的にキャスト（None混在でobject dtypeになるのを防ぐ）
    numeric_cols = [c for c in df.columns if c != "会社名"]
    df[numeric_cols] = df[numeric_cols].apply(pd.to_numeric, errors="coerce")
    return df


def radar_metrics(summary_df: pd.DataFrame) -> pd.DataFrame:
    """
    レーダーチャート用に正規化した指標DataFrameを返す
    各指標を0〜100にスケールし、方向を統一する（大きいほど良い）
    """
    cols = [
        "売上成長率(%)",
        "営業利益率(%)",
        "ROE(%)",
        "ROA(%)",
        "自己資本比率(%)",
        "PER",
        "PBR",
    ]
    df = summary_df[cols].copy().apply(pd.to_numeric, errors="coerce")

    # PER・PBRは低い方が割安なので反転
    for invert_col in ["PER", "PBR"]:
        if invert_col in df.columns:
            df[invert_col] = df[invert_col].max() + df[invert_col].min() - df[invert_col]

    # min-maxスケーリング（0〜100）
    for col in df.columns:
        col_min = df[col].min()
        col_max = df[col].max()
        if col_max != col_min:
            df[col] = (df[col] - col_min) / (col_max - col_min) * 100
        else:
            df[col] = 50.0  # 全社同値なら中間値

    return df
