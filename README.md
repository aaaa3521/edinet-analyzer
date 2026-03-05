# EDINET 財務分析ダッシュボード

EDINET API と Yahoo Finance を使って、日本の上場企業の財務データを取得し、
投資判断・競合比較ができる Streamlit ダッシュボード。

## セットアップ

```bash
cd edinet-analyzer
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env
# .env を編集して EDINET_API_KEY を設定
```

## 起動

```bash
streamlit run app.py
```

## EDINET API キーの取得

1. https://disclosure2.edinet-fsa.go.jp/ にアクセス
2. 「APIキー申請」から申請（無料）
3. 取得したキーを `.env` または サイドバーの入力欄に設定

> **注意:** APIキーなしでも Yahoo Finance データ（株価・PER・PBR）は取得できます。
> EDINET データ（売上・営業利益等）の取得には APIキーが必要です。

## ディレクトリ構成

```
edinet-analyzer/
├── app.py              # Streamlit メインアプリ
├── src/
│   ├── edinet.py       # EDINET API クライアント
│   ├── yahoo_finance.py # 株価・PER・PBR 取得
│   └── metrics.py      # 指標計算ロジック
├── requirements.txt
└── .env.example
```

## 機能

- 複数証券コードの同時比較（2〜5社推奨）
- EDINET から財務三表データを取得（売上・営業利益・純利益・総資産・自己資本・有利子負債）
- Yahoo Finance から株価・PER・PBR をリアルタイム取得
- 収益性指標：売上成長率・営業利益率・ROE・ROA
- 安全性指標：自己資本比率・D/E レシオ
- バリュエーション：PER・PBR・EPS
- Plotly グラフ + PNG ダウンロード
- レーダーチャートによる競合比較
- Excel エクスポート（全シート）
