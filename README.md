# EDINET 財務分析ダッシュボード

**日本の上場企業を証券コードで検索し、財務三表・株価・バリュエーションを自動取得してインタラクティブに比較分析できる Web アプリ。**

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.32+-FF4B4B?logo=streamlit&logoColor=white)](https://streamlit.io/)
[![Plotly](https://img.shields.io/badge/Plotly-5.20+-3F4F75?logo=plotly&logoColor=white)](https://plotly.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## デモ

> スクリーンショットは `docs/screenshots/` に配置しています。

### ダッシュボード概要

![概要タブ]
<img width="2110" height="1031" alt="image" src="https://github.com/user-attachments/assets/7165e224-a013-4ca9-895f-256c112dad29" />


### 競合レーダーチャート（トヨタ・ホンダ・マツダ）

![レーダーチャート](docs/screenshots/radar.png)

### 株価パフォーマンス比較

![株価推移](docs/screenshots/stock.png)

### 収益性・安全性グラフ

![収益性](docs/screenshots/profitability.png)

---

## 概要

| 項目 | 内容 |
|------|------|
| データソース | [EDINET API](https://disclosure2.edinet-fsa.go.jp/)（有価証券報告書）/ Yahoo Finance |
| 対象企業 | 日本の上場企業（証券コード指定） |
| 同時比較 | 最大5社 |
| 出力形式 | インタラクティブグラフ / PNG / Excel |

---

## 機能一覧

### データ取得
- **EDINET API** から有価証券報告書（XBRL形式）を自動取得・解析
  - 売上高 / 営業利益 / 純利益 / 総資産 / 自己資本 / 有利子負債
- **Yahoo Finance** からリアルタイム株価・バリュエーション指標を取得
  - 株価 / 時価総額 / PER / PBR / EPS / 配当利回り

### 分析指標

| カテゴリ | 指標 |
|----------|------|
| 収益性 | 売上成長率・営業利益率・ROE・ROA |
| 安全性 | 自己資本比率・D/E レシオ |
| バリュエーション | PER・PBR・EPS・配当利回り |

### ビジュアライゼーション
- 各指標のバーチャート・散布図（Plotly）
- 株価時系列グラフ + 正規化パフォーマンス比較
- **レーダーチャート**による多角的な競合比較
- グラフごとの **PNG ダウンロードボタン**
- **Excel エクスポート**（収益性・安全性・バリュエーション・株価履歴を別シートで出力）

---

## 技術スタック

| 役割 | ライブラリ |
|------|-----------|
| UI フレームワーク | Streamlit |
| グラフ描画 | Plotly |
| データ処理 | pandas |
| 株価取得 | yfinance |
| EDINET API 通信 | requests |
| XBRL 解析 | xml.etree.ElementTree |
| Excel 出力 | openpyxl |
| PNG 出力 | kaleido |

---

## セットアップ

### 1. リポジトリのクローン

```bash
git clone https://github.com/aaaa3521/edinet-analyzer.git
cd edinet-analyzer
```

### 2. 仮想環境の作成と依存パッケージのインストール

```bash
python -m venv .venv

# Mac / Linux
source .venv/bin/activate

# Windows
.venv\Scripts\activate

pip install -r requirements.txt
```

### 3. 環境変数の設定（任意）

```bash
cp .env.example .env
# .env を開いて EDINET_API_KEY を設定
```

> **APIキーなしでも動作します。**
> Yahoo Finance データ（株価・PER・PBR）は常に取得可能です。
> EDINET データ（売上・利益等）の取得には無料の API キーが必要です。

### 4. 起動

```bash
streamlit run app.py
```

ブラウザで `http://localhost:8501` が自動的に開きます。

---

## 使い方

1. サイドバーに **証券コード** を1行1コードで入力（例: トヨタ `7203`、ホンダ `7267`、マツダ `7261`）
2. 必要に応じて **EDINET API キー** を入力
3. **「データ取得・分析」** ボタンを押す
4. 7つのタブで分析結果を確認

| タブ | 内容 |
|------|------|
| 概要 | 企業サマリー・時価総額比較 |
| 収益性 | 営業利益率・ROE・ROA・P/L比較 |
| 安全性 | 自己資本比率・D/Eレシオ・B/S比較 |
| バリュエーション | PER・PBR・散布図 |
| 株価推移 | 時系列グラフ・正規化パフォーマンス比較 |
| レーダー比較 | 多軸レーダーチャートによる総合比較 |
| エクスポート | Excel ダウンロード・全指標プレビュー |

---

## EDINET API キーの取得方法

1. [EDINET](https://disclosure2.edinet-fsa.go.jp/) にアクセス
2. 「API キー申請」から申請（**無料・即日発行**）
3. 発行されたキーを `.env` ファイルまたはサイドバーの入力欄に設定

---

## ディレクトリ構成

```
edinet-analyzer/
├── app.py                  # Streamlit メインアプリ（UI・タブ構成）
├── src/
│   ├── edinet.py           # EDINET API クライアント・XBRL 解析
│   ├── yahoo_finance.py    # 株価・PER・PBR・EPS 取得
│   └── metrics.py          # 財務指標計算・DataFrame 生成
├── docs/
│   └── screenshots/        # README 用スクリーンショット
├── requirements.txt
├── .env.example
└── README.md
```

---

## ライセンス

MIT License — 自由に利用・改変・配布できます。

---

## 作者

**aaaa3521** — [GitHub](https://github.com/aaaa3521)
