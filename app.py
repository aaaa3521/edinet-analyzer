"""
EDINET財務分析ダッシュボード
Streamlitメインアプリ
"""

import io
import os
import time

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv

from src.edinet import EdinetClient
from src.yahoo_finance import get_multi_stock_info, get_price_history, get_income_history
from src.metrics import build_summary_df, radar_metrics

load_dotenv()

# ──────────────────────────────────────────────
# ページ設定
# ──────────────────────────────────────────────
st.set_page_config(
    page_title="EDINET 財務分析ダッシュボード",
    page_icon="📊",
    layout="wide",
)

st.title("📊 EDINET 財務分析ダッシュボード")
st.caption("EDINET API + Yahoo Finance を使って日本の上場企業を比較分析します")

# ──────────────────────────────────────────────
# サイドバー: 入力
# ──────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ 設定")
    api_key = st.text_input(
        "EDINET APIキー",
        value=os.getenv("EDINET_API_KEY", ""),
        type="password",
        help="https://disclosure2.edinet-fsa.go.jp/ で取得",
    )
    raw_codes = st.text_area(
        "証券コード（1行1コード、2〜5社）",
        value="7203\n7267\n7261",
        height=120,
        help="例: トヨタ=7203, ホンダ=7267, マツダ=7261",
    )
    price_period = st.selectbox(
        "株価表示期間",
        options=["6mo", "1y", "2y", "5y"],
        index=1,
        format_func=lambda x: {"6mo": "6ヶ月", "1y": "1年", "2y": "2年", "5y": "5年"}[x],
    )
    run = st.button("🔍 データ取得・分析", use_container_width=True, type="primary")

securities_codes = [c.strip() for c in raw_codes.splitlines() if c.strip()]

if not run:
    st.info("サイドバーで証券コードを入力し、「データ取得・分析」ボタンを押してください。")
    st.stop()

if len(securities_codes) < 1:
    st.error("証券コードを1つ以上入力してください。")
    st.stop()

# ──────────────────────────────────────────────
# データ取得
# ──────────────────────────────────────────────
edinet = EdinetClient(api_key=api_key)

companies_data: dict[str, dict] = {}
price_histories: dict[str, pd.DataFrame] = {}
income_histories: dict[str, pd.DataFrame] = {}

progress = st.progress(0, text="データ取得中...")
total = len(securities_codes)

for i, code in enumerate(securities_codes):
    progress.progress((i) / total, text=f"{code} のデータを取得中...")

    # Yahoo Finance
    stock_info = get_multi_stock_info([code])[code]
    price_histories[code] = get_price_history(code, period=price_period)
    income_histories[code] = get_income_history(code)

    # EDINET (APIキーがある場合のみ)
    financials: dict = {}
    if api_key:
        with st.spinner(f"{code}: EDINETから財務データを取得中（時間がかかる場合があります）..."):
            financials = edinet.get_financials(code)
        if "_error" in financials:
            st.warning(f"{code}: {financials['_error']}")
            financials = {}
        elif financials:
            got = [k for k in financials if not k.startswith("_")]
            st.success(f"{code}: EDINET取得成功 → {', '.join(got)}")
    else:
        st.warning(f"{code}: EDINETキー未設定のためYahoo Financeデータのみ使用します")

    companies_data[code] = {
        "financials": financials,
        "stock_info": stock_info,
    }

progress.progress(1.0, text="取得完了")
time.sleep(0.3)
progress.empty()

# ──────────────────────────────────────────────
# サマリーDataFrame
# ──────────────────────────────────────────────
summary_df = build_summary_df(companies_data)

# ──────────────────────────────────────────────
# ヘルパー: グラフPNGダウンロードボタン
# ──────────────────────────────────────────────
def download_png_button(fig: go.Figure, filename: str, key: str):
    try:
        img_bytes = fig.to_image(format="png", width=1200, height=600, scale=2)
        st.download_button(
            label="📥 PNG ダウンロード",
            data=img_bytes,
            file_name=filename,
            mime="image/png",
            key=key,
        )
    except Exception:
        st.caption("PNG出力にはkaleido>=0.2.1が必要です: `pip install kaleido`")


# ──────────────────────────────────────────────
# タブ構成
# ──────────────────────────────────────────────
tab_overview, tab_trend, tab_profit, tab_safety, tab_valuation, tab_stock, tab_radar, tab_export = st.tabs(
    ["概要", "業績推移", "収益性", "安全性", "バリュエーション", "株価推移", "レーダー比較", "エクスポート"]
)

# ========== 概要タブ ==========
with tab_overview:
    st.subheader("企業概要サマリー")

    overview_cols = ["会社名", "株価", "時価総額", "売上高", "営業利益", "純利益"]
    available = [c for c in overview_cols if c in summary_df.columns]
    st.dataframe(
        summary_df[available].style.format(
            {
                "株価": "{:,.0f}",
                "時価総額": "{:,.0f}",
                "売上高": "{:,.0f}",
                "営業利益": "{:,.0f}",
                "純利益": "{:,.0f}",
            },
            na_rep="N/A",
        ),
        use_container_width=True,
    )

    # 時価総額バーチャート
    mc_data = summary_df[["会社名", "時価総額"]].dropna()
    if not mc_data.empty:
        fig_mc = px.bar(
            mc_data.reset_index(),
            x="会社名",
            y="時価総額",
            color="証券コード",
            title="時価総額比較",
            labels={"時価総額": "時価総額 (円)"},
            text_auto=True,
        )
        st.plotly_chart(fig_mc, use_container_width=True)
        download_png_button(fig_mc, "market_cap.png", "dl_mc")

# ========== 業績推移タブ ==========
with tab_trend:
    st.subheader("業績推移（年次・最大4期）")
    st.caption("出典: Yahoo Finance　※経常利益は税引前利益で近似")

    METRICS = ["売上高", "営業利益", "税引前利益(経常利益近似)", "当期純利益"]
    UNIT = 1_000_000  # 百万円単位で表示

    # ── 各社の個別テーブル ──
    for code, df_inc in income_histories.items():
        name = companies_data[code]["stock_info"].get("company_name", code)
        st.markdown(f"#### {name}（{code}）")
        if df_inc.empty:
            st.warning("データを取得できませんでした")
            continue

        display = df_inc.copy()
        display.index = display.index.strftime("%Y年%m月期")
        display = display / UNIT  # 百万円換算
        available_cols = [c for c in METRICS if c in display.columns]
        st.dataframe(
            display[available_cols].style.format("{:,.0f}", na_rep="N/A"),
            use_container_width=True,
        )
        st.caption("単位: 百万円")

    st.divider()

    # ── 指標別・複数社比較グラフ ──
    st.subheader("指標別グラフ（複数社比較）")

    for metric in METRICS:
        series_list = []
        for code, df_inc in income_histories.items():
            if df_inc.empty or metric not in df_inc.columns:
                continue
            name = companies_data[code]["stock_info"].get("company_name", code)
            s = (df_inc[metric] / UNIT).rename(f"{name}（{code}）")
            series_list.append(s)

        if not series_list:
            continue

        plot_df = pd.concat(series_list, axis=1)
        plot_df.index = plot_df.index.strftime("%Y年%m月期")

        fig = go.Figure()
        for col in plot_df.columns:
            fig.add_trace(go.Bar(
                name=col,
                x=plot_df.index,
                y=plot_df[col],
                text=plot_df[col].apply(lambda v: f"{v:,.0f}" if pd.notna(v) else ""),
                textposition="outside",
            ))
        fig.update_layout(
            title=f"{metric}の推移（百万円）",
            xaxis_title="会計年度",
            yaxis_title="金額（百万円）",
            barmode="group",
            legend_title="銘柄",
            hovermode="x unified",
        )
        st.plotly_chart(fig, use_container_width=True)
        download_png_button(fig, f"trend_{metric}.png", f"dl_trend_{metric}")

    # ── 売上成長率の折れ線グラフ ──
    st.subheader("売上成長率の推移（前期比）")
    growth_series = []
    for code, df_inc in income_histories.items():
        if df_inc.empty or "売上高" not in df_inc.columns:
            continue
        name = companies_data[code]["stock_info"].get("company_name", code)
        growth = df_inc["売上高"].pct_change() * 100
        growth.index = df_inc.index.strftime("%Y年%m月期")
        growth_series.append(growth.rename(f"{name}（{code}）"))

    if growth_series:
        growth_df = pd.concat(growth_series, axis=1).dropna(how="all")
        fig_growth = go.Figure()
        for col in growth_df.columns:
            fig_growth.add_trace(go.Scatter(
                x=growth_df.index, y=growth_df[col],
                mode="lines+markers+text",
                name=col,
                text=growth_df[col].apply(lambda v: f"{v:.1f}%" if pd.notna(v) else ""),
                textposition="top center",
            ))
        fig_growth.add_hline(y=0, line_dash="dash", line_color="gray")
        fig_growth.update_layout(
            title="売上成長率（前期比 %）",
            xaxis_title="会計年度",
            yaxis_title="成長率（%）",
            hovermode="x unified",
        )
        st.plotly_chart(fig_growth, use_container_width=True)
        download_png_button(fig_growth, "sales_growth.png", "dl_growth")

    # ── 利益率の折れ線グラフ ──
    st.divider()
    st.subheader("利益率の推移")

    MARGIN_METRICS = [
        ("営業利益",              "営業利益率（%）"),
        ("税引前利益(経常利益近似)", "経常利益率（%）"),
        ("当期純利益",             "純利益率（%）"),
    ]

    col_left, col_right = st.columns(2)
    margin_figs = []

    for i, (profit_col, margin_label) in enumerate(MARGIN_METRICS):
        margin_series = []
        for code, df_inc in income_histories.items():
            if df_inc.empty:
                continue
            if "売上高" not in df_inc.columns or profit_col not in df_inc.columns:
                continue
            name = companies_data[code]["stock_info"].get("company_name", code)
            margin = (df_inc[profit_col] / df_inc["売上高"] * 100)
            margin.index = df_inc.index.strftime("%Y年%m月期")
            margin_series.append(margin.rename(f"{name}（{code}）"))

        if not margin_series:
            continue

        margin_df = pd.concat(margin_series, axis=1).dropna(how="all")
        fig_m = go.Figure()
        for col in margin_df.columns:
            fig_m.add_trace(go.Scatter(
                x=margin_df.index,
                y=margin_df[col],
                mode="lines+markers+text",
                name=col,
                text=margin_df[col].apply(lambda v: f"{v:.1f}%" if pd.notna(v) else ""),
                textposition="top center",
            ))
        fig_m.add_hline(y=0, line_dash="dash", line_color="gray")
        fig_m.update_layout(
            title=margin_label + "の推移",
            xaxis_title="会計年度",
            yaxis_title=margin_label,
            hovermode="x unified",
            legend_title="銘柄",
        )
        margin_figs.append((fig_m, margin_label))

    # 2列レイアウトで表示
    for i, (fig_m, margin_label) in enumerate(margin_figs):
        safe_key = margin_label.replace("（", "_").replace("）", "_").replace("%", "pct")
        if i % 2 == 0:
            col_left, col_right = st.columns(2)
        target_col = col_left if i % 2 == 0 else col_right
        with target_col:
            st.plotly_chart(fig_m, use_container_width=True)
            download_png_button(fig_m, f"margin_{safe_key}.png", f"dl_margin_{safe_key}")

# ========== 収益性タブ ==========
with tab_profit:
    st.subheader("収益性指標")

    profit_cols = ["会社名", "売上成長率(%)", "営業利益率(%)", "ROE(%)", "ROA(%)"]
    available = [c for c in profit_cols if c in summary_df.columns]
    _profit_fmt = {c: "{:.2f}" for c in ["売上成長率(%)", "営業利益率(%)", "ROE(%)", "ROA(%)"] if c in available}
    st.dataframe(
        summary_df[available].style.format(_profit_fmt, na_rep="N/A"),
        use_container_width=True,
    )

    col1, col2 = st.columns(2)

    with col1:
        margin_data = summary_df[["会社名", "営業利益率(%)"]].dropna()
        if not margin_data.empty:
            fig_margin = px.bar(
                margin_data.reset_index(),
                x="会社名",
                y="営業利益率(%)",
                color="証券コード",
                title="営業利益率比較",
                text_auto=".2f",
            )
            st.plotly_chart(fig_margin, use_container_width=True)
            download_png_button(fig_margin, "operating_margin.png", "dl_margin")

    with col2:
        roe_roa = summary_df[["会社名", "ROE(%)", "ROA(%)"]].dropna(how="all", subset=["ROE(%)", "ROA(%)"])
        if not roe_roa.empty:
            fig_roe = px.bar(
                roe_roa.reset_index().melt(id_vars=["証券コード", "会社名"], var_name="指標", value_name="値"),
                x="会社名",
                y="値",
                color="指標",
                barmode="group",
                title="ROE / ROA 比較",
                text_auto=".2f",
            )
            st.plotly_chart(fig_roe, use_container_width=True)
            download_png_button(fig_roe, "roe_roa.png", "dl_roe")

    # 売上・営業利益・純利益 グループバー
    pl_cols = ["会社名", "売上高", "営業利益", "純利益"]
    available_pl = [c for c in pl_cols if c in summary_df.columns]
    pl_data = summary_df[available_pl].dropna(how="all", subset=["売上高"])
    if not pl_data.empty:
        fig_pl = px.bar(
            pl_data.reset_index().melt(id_vars=["証券コード", "会社名"], var_name="項目", value_name="金額"),
            x="会社名",
            y="金額",
            color="項目",
            barmode="group",
            title="損益比較（売上・営業利益・純利益）",
            labels={"金額": "金額 (円)"},
        )
        st.plotly_chart(fig_pl, use_container_width=True)
        download_png_button(fig_pl, "pl_comparison.png", "dl_pl")

# ========== 安全性タブ ==========
with tab_safety:
    st.subheader("安全性指標")

    safety_cols = ["会社名", "総資産", "自己資本", "有利子負債", "自己資本比率(%)", "D/Eレシオ"]
    available = [c for c in safety_cols if c in summary_df.columns]
    st.dataframe(
        summary_df[available].style.format(
            {
                "総資産": "{:,.0f}",
                "自己資本": "{:,.0f}",
                "有利子負債": "{:,.0f}",
                "自己資本比率(%)": "{:.2f}",
                "D/Eレシオ": "{:.2f}",
            },
            na_rep="N/A",
        ),
        use_container_width=True,
    )

    col1, col2 = st.columns(2)

    with col1:
        er_data = summary_df[["会社名", "自己資本比率(%)"]].dropna()
        if not er_data.empty:
            fig_er = px.bar(
                er_data.reset_index(),
                x="会社名",
                y="自己資本比率(%)",
                color="証券コード",
                title="自己資本比率比較",
                text_auto=".1f",
            )
            fig_er.add_hline(y=50, line_dash="dash", line_color="red", annotation_text="50%基準")
            st.plotly_chart(fig_er, use_container_width=True)
            download_png_button(fig_er, "equity_ratio.png", "dl_er")

    with col2:
        de_data = summary_df[["会社名", "D/Eレシオ"]].dropna()
        if not de_data.empty:
            fig_de = px.bar(
                de_data.reset_index(),
                x="会社名",
                y="D/Eレシオ",
                color="証券コード",
                title="D/Eレシオ比較（低い方が財務健全）",
                text_auto=".2f",
            )
            st.plotly_chart(fig_de, use_container_width=True)
            download_png_button(fig_de, "de_ratio.png", "dl_de")

    # 総資産 / 自己資本 / 有利子負債 積み上げバー
    bs_cols = ["会社名", "自己資本", "有利子負債"]
    available_bs = [c for c in bs_cols if c in summary_df.columns]
    bs_data = summary_df[available_bs].dropna(how="all", subset=["自己資本"])
    if not bs_data.empty:
        fig_bs = px.bar(
            bs_data.reset_index().melt(id_vars=["証券コード", "会社名"], var_name="項目", value_name="金額"),
            x="会社名",
            y="金額",
            color="項目",
            barmode="group",
            title="自己資本 vs 有利子負債",
            labels={"金額": "金額 (円)"},
        )
        st.plotly_chart(fig_bs, use_container_width=True)
        download_png_button(fig_bs, "balance_sheet.png", "dl_bs")

# ========== バリュエーションタブ ==========
with tab_valuation:
    st.subheader("バリュエーション指標")

    val_cols = ["会社名", "PER", "PBR", "EPS", "配当利回り(%)"]
    available = [c for c in val_cols if c in summary_df.columns]
    st.dataframe(
        summary_df[available].style.format(
            {"PER": "{:.2f}", "PBR": "{:.2f}", "EPS": "{:.2f}", "配当利回り(%)": "{:.2f}"},
            na_rep="N/A",
        ),
        use_container_width=True,
    )

    col1, col2 = st.columns(2)

    with col1:
        per_data = summary_df[["会社名", "PER"]].dropna()
        if not per_data.empty:
            fig_per = px.bar(
                per_data.reset_index(),
                x="会社名",
                y="PER",
                color="証券コード",
                title="PER比較（株価収益率）",
                text_auto=".1f",
            )
            st.plotly_chart(fig_per, use_container_width=True)
            download_png_button(fig_per, "per.png", "dl_per")

    with col2:
        pbr_data = summary_df[["会社名", "PBR"]].dropna()
        if not pbr_data.empty:
            fig_pbr = px.bar(
                pbr_data.reset_index(),
                x="会社名",
                y="PBR",
                color="証券コード",
                title="PBR比較（株価純資産倍率）",
                text_auto=".2f",
            )
            fig_pbr.add_hline(y=1, line_dash="dash", line_color="red", annotation_text="PBR=1倍")
            st.plotly_chart(fig_pbr, use_container_width=True)
            download_png_button(fig_pbr, "pbr.png", "dl_pbr")

    # PER vs PBR 散布図（3社以上の場合に有用）
    scatter_data = summary_df[["会社名", "PER", "PBR"]].dropna()
    if len(scatter_data) >= 2:
        fig_scatter = px.scatter(
            scatter_data.reset_index(),
            x="PER",
            y="PBR",
            text="会社名",
            color="証券コード",
            title="PER vs PBR 散布図",
            size_max=20,
        )
        fig_scatter.update_traces(textposition="top center", marker_size=15)
        st.plotly_chart(fig_scatter, use_container_width=True)
        download_png_button(fig_scatter, "per_pbr_scatter.png", "dl_scatter")

# ========== 株価推移タブ ==========
with tab_stock:
    st.subheader("株価推移")

    fig_price = go.Figure()
    for code, df_price in price_histories.items():
        if df_price.empty:
            st.warning(f"{code}: 株価データを取得できませんでした")
            continue
        name = companies_data[code]["stock_info"].get("company_name", code)
        fig_price.add_trace(
            go.Scatter(
                x=df_price.index,
                y=df_price["Close"],
                mode="lines",
                name=f"{name} ({code})",
            )
        )

    fig_price.update_layout(
        title=f"株価推移（終値・月次）",
        xaxis_title="日付",
        yaxis_title="株価 (円)",
        legend_title="銘柄",
        hovermode="x unified",
    )
    st.plotly_chart(fig_price, use_container_width=True)
    download_png_button(fig_price, "stock_price.png", "dl_price")

    # 正規化比較（初日=100）
    fig_norm = go.Figure()
    for code, df_price in price_histories.items():
        if df_price.empty:
            continue
        name = companies_data[code]["stock_info"].get("company_name", code)
        base = df_price["Close"].iloc[0]
        if base and base != 0:
            normalized = df_price["Close"] / base * 100
            fig_norm.add_trace(
                go.Scatter(
                    x=df_price.index,
                    y=normalized,
                    mode="lines",
                    name=f"{name} ({code})",
                )
            )

    fig_norm.update_layout(
        title="株価パフォーマンス比較（初日=100に正規化）",
        xaxis_title="日付",
        yaxis_title="相対パフォーマンス",
        hovermode="x unified",
    )
    fig_norm.add_hline(y=100, line_dash="dash", line_color="gray")
    st.plotly_chart(fig_norm, use_container_width=True)
    download_png_button(fig_norm, "stock_normalized.png", "dl_norm")

# ========== レーダーチャートタブ ==========
with tab_radar:
    st.subheader("競合レーダーチャート（正規化スコア）")
    st.caption("各指標を0〜100に正規化。PER・PBRは低い方が高スコア。")

    try:
        radar_df = radar_metrics(summary_df)
    except Exception as e:
        st.error(f"レーダーチャート計算エラー: {e}")
        radar_df = pd.DataFrame()

    if not radar_df.empty:
        categories = list(radar_df.columns)

        fig_radar = go.Figure()
        colors = px.colors.qualitative.Plotly
        for i, (code, row) in enumerate(radar_df.iterrows()):
            name = summary_df.loc[code, "会社名"] if code in summary_df.index else code
            values = row.tolist()
            fig_radar.add_trace(
                go.Scatterpolar(
                    r=values + [values[0]],
                    theta=categories + [categories[0]],
                    fill="toself",
                    name=f"{name} ({code})",
                    fillcolor=colors[i % len(colors)],
                    opacity=0.3,
                    line=dict(color=colors[i % len(colors)]),
                )
            )

        fig_radar.update_layout(
            polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
            title="競合比較レーダーチャート",
            showlegend=True,
        )
        st.plotly_chart(fig_radar, use_container_width=True)
        download_png_button(fig_radar, "radar_chart.png", "dl_radar")

        st.subheader("スコア一覧")
        st.dataframe(
            radar_df.style.format("{:.1f}").background_gradient(cmap="RdYlGn", axis=0),
            use_container_width=True,
        )
    else:
        st.info("指標データが不足しているためレーダーチャートを生成できません。")

# ========== エクスポートタブ ==========
with tab_export:
    st.subheader("Excelエクスポート")

    @st.cache_data
    def generate_excel(df: pd.DataFrame, price_dict: dict) -> bytes:
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            # サマリーシート
            df.reset_index().to_excel(writer, sheet_name="財務サマリー", index=False)

            # 収益性シート
            profit_cols = ["会社名", "売上高", "営業利益", "純利益", "売上成長率(%)", "営業利益率(%)", "ROE(%)", "ROA(%)"]
            available = [c for c in profit_cols if c in df.columns]
            df[available].reset_index().to_excel(writer, sheet_name="収益性", index=False)

            # 安全性シート
            safety_cols = ["会社名", "総資産", "自己資本", "有利子負債", "自己資本比率(%)", "D/Eレシオ"]
            available = [c for c in safety_cols if c in df.columns]
            df[available].reset_index().to_excel(writer, sheet_name="安全性", index=False)

            # バリュエーションシート
            val_cols = ["会社名", "株価", "時価総額", "PER", "PBR", "EPS", "配当利回り(%)"]
            available = [c for c in val_cols if c in df.columns]
            df[available].reset_index().to_excel(writer, sheet_name="バリュエーション", index=False)

            # 株価履歴シート（各社）
            for code, df_price in price_dict.items():
                if df_price.empty:
                    continue
                sheet_name = f"株価_{code}"[:31]  # Excelシート名31文字制限
                df_price.reset_index().to_excel(writer, sheet_name=sheet_name, index=False)

        return buf.getvalue()

    excel_bytes = generate_excel(summary_df, price_histories)
    st.download_button(
        label="📥 Excelファイルをダウンロード",
        data=excel_bytes,
        file_name="financial_analysis.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    st.subheader("データプレビュー（全指標）")
    st.dataframe(
        summary_df.style.format(
            {
                "株価": "{:,.0f}",
                "時価総額": "{:,.0f}",
                "売上高": "{:,.0f}",
                "営業利益": "{:,.0f}",
                "純利益": "{:,.0f}",
                "総資産": "{:,.0f}",
                "自己資本": "{:,.0f}",
                "有利子負債": "{:,.0f}",
                "売上成長率(%)": "{:.2f}",
                "営業利益率(%)": "{:.2f}",
                "ROE(%)": "{:.2f}",
                "ROA(%)": "{:.2f}",
                "自己資本比率(%)": "{:.2f}",
                "D/Eレシオ": "{:.2f}",
                "PER": "{:.2f}",
                "PBR": "{:.2f}",
                "EPS": "{:.2f}",
                "配当利回り(%)": "{:.2f}",
            },
            na_rep="N/A",
        ),
        use_container_width=True,
    )
