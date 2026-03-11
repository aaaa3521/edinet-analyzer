"""
EDINET APIクライアント
EDINETから財務三表データを取得する
"""

import os
import requests
import zipfile
import io
import json
from datetime import date, timedelta
from typing import Optional
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

EDINET_API_BASE = "https://disclosure.edinet-fsa.go.jp/api/v2"


class EdinetClient:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("EDINET_API_KEY", "")
        self.session = requests.Session()

    def _get(self, url: str, params: dict) -> requests.Response:
        if self.api_key:
            params["Subscription-Key"] = self.api_key
        resp = self.session.get(url, params=params, timeout=30)
        resp.raise_for_status()
        return resp

    def get_documents_list(self, target_date: date) -> list[dict]:
        """指定日の書類一覧を取得する"""
        url = f"{EDINET_API_BASE}/documents.json"
        params = {"date": target_date.strftime("%Y-%m-%d"), "type": 2}
        resp = self._get(url, params)
        data = resp.json()
        return data.get("results", [])

    def find_docid_by_securities_code(
        self, securities_code: str, doc_type_code: str = "120"
    ) -> Optional[str]:
        """
        証券コードから直近の有価証券報告書のdocIDを探す
        doc_type_code: 120=有価証券報告書, 130=四半期報告書

        戦略:
        1. 有価証券報告書は決算月の約3ヶ月後に提出される
           （例: 3月決算 → 6月提出）
        2. 1日ずつ遡ると最大500回APIを叩くため、
           提出件数が多い「月末前後の平日」を週単位でサンプリングする
        3. それでも見つからなければ直近90日を日次で精査する
        """
        # 5桁コード（EDINETは末尾0を付加）にも対応
        code5 = securities_code.zfill(5) if len(securities_code) == 4 else securities_code

        def _matches(doc: dict) -> bool:
            sec = doc.get("secCode") or ""
            return (
                sec.startswith(securities_code) or sec == code5
            ) and doc.get("docTypeCode") == doc_type_code

        today = date.today()

        # ── フェーズ1: 週単位で最大2年分をサンプリング ──
        for weeks_back in range(0, 104):
            target = today - timedelta(weeks=weeks_back)
            # 平日に補正（土→金、日→月）
            if target.weekday() == 5:
                target -= timedelta(days=1)
            elif target.weekday() == 6:
                target += timedelta(days=1)
            try:
                docs = self.get_documents_list(target)
            except Exception:
                continue
            for doc in docs:
                if _matches(doc):
                    return doc["docID"]

        # ── フェーズ2: 直近90日を日次で精査（週サンプリングの漏れを補完）──
        for days_back in range(0, 90):
            target = today - timedelta(days=days_back)
            try:
                docs = self.get_documents_list(target)
            except Exception:
                continue
            for doc in docs:
                if _matches(doc):
                    return doc["docID"]

        return None

    def download_xbrl_zip(self, doc_id: str) -> Optional[bytes]:
        """書類のXBRL ZIPをダウンロードする"""
        url = f"{EDINET_API_BASE}/documents/{doc_id}"
        params = {"type": 1}
        try:
            resp = self._get(url, params)
            return resp.content
        except Exception:
            return None

    def extract_financials_from_zip(self, zip_bytes: bytes) -> dict:
        """
        ZIPからiXBRL/XBRLを解析して財務データを抽出する
        返り値: {label: value, ...}
        """
        results = {}
        try:
            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
                names = zf.namelist()

                # PublicDoc 内の iXBRL(.htm) を優先、次に .xbrl
                candidates = (
                    [n for n in names if "PublicDoc" in n and n.endswith(".htm")]
                    or [n for n in names if "PublicDoc" in n and n.endswith(".xbrl")]
                    or [n for n in names if n.endswith(".htm")]
                    or [n for n in names if n.endswith(".xbrl")]
                )

                if not candidates:
                    return {"_error": "XBRLファイルが見つかりません", "_files": str(names[:10])}

                key_fields = {"net_sales", "operating_income", "net_income", "total_assets", "equity"}
                for fname in candidates:
                    with zf.open(fname) as f:
                        content = f.read().decode("utf-8", errors="ignore")
                    parsed = _parse_xbrl_content(content)
                    for k, v in parsed.items():
                        if k not in results:
                            results[k] = v
                    # 全主要項目が揃ったら終了（揃わなければ全ファイルを走査）
                    if key_fields.issubset(results.keys()):
                        break

        except Exception as e:
            results["_error"] = str(e)
        return results

    def get_financials(self, securities_code: str) -> dict:
        """
        証券コードから財務データを一括取得する
        取得できなかった項目はNoneになる
        """
        doc_id = self.find_docid_by_securities_code(securities_code)
        if doc_id is None:
            return {"_error": f"{securities_code}: 有価証券報告書が見つかりませんでした"}

        zip_bytes = self.download_xbrl_zip(doc_id)
        if zip_bytes is None:
            return {"_error": f"{securities_code}: ZIPダウンロードに失敗しました"}

        return self.extract_financials_from_zip(zip_bytes)


# XBRL要素名と内部キーのマッピング（JP-GAAP / IFRS 両対応）
_XBRL_FIELD_MAP = {
    # ── 売上高 ──────────────────────────────
    "NetSales": "net_sales",                                    # JP-GAAP
    "NetSalesOfCompletedConstructionContracts": "net_sales",    # JP-GAAP 工事
    "Revenue": "net_sales",                                     # IFRS
    "RevenueIFRS": "net_sales",                                 # IFRS (旧)
    "NetRevenue": "net_sales",
    "OperatingRevenue": "net_sales",
    # ── 営業利益 ─────────────────────────────
    "OperatingIncome": "operating_income",                      # JP-GAAP
    "OperatingProfit": "operating_income",                      # IFRS
    "OperatingProfitLoss": "operating_income",                  # IFRS
    "ProfitFromOperatingActivities": "operating_income",        # IFRS
    "OperatingProfitIFRS": "operating_income",
    # ── 純利益 ──────────────────────────────
    "ProfitLoss": "net_income",                                 # JP-GAAP / IFRS
    "ProfitLossAttributableToOwnersOfParent": "net_income",     # JP-GAAP 連結
    "ProfitLossAttributableToOwnersOfParentIFRS": "net_income", # IFRS 連結
    "NetIncomeLoss": "net_income",
    "Profit": "net_income",                                     # IFRS 簡略
    # ── 総資産 ──────────────────────────────
    "Assets": "total_assets",                                   # JP-GAAP / IFRS
    "TotalAssets": "total_assets",
    # ── 自己資本 ─────────────────────────────
    "Equity": "equity",                                         # IFRS
    "NetAssets": "equity",                                      # JP-GAAP
    "EquityAttributableToOwnersOfParent": "equity",             # IFRS 連結
    "TotalNetAssets": "equity",
    # ── 有利子負債 ───────────────────────────
    "InterestBearingDebt": "interest_bearing_debt",
    "BorrowingsAndBondsPayable": "interest_bearing_debt",
    "InterestBearingLiabilities": "interest_bearing_debt",
    "BorrowingsIFRS": "interest_bearing_debt",
    "Borrowings": "interest_bearing_debt",
    # ── EPS / 株式数 ─────────────────────────
    "EarningsPerShare": "eps",
    "BasicEarningsLossPerShare": "eps",
    "BasicEarningsPerShare": "eps",
    "NumberOfSharesOutstanding": "shares_outstanding",
}


def _parse_xbrl_content(content: str) -> dict:
    """
    iXBRL / XBRL から財務数値を抽出する
    BeautifulSoup で HTML/XML を柔軟にパースし、
    ix:nonFraction 要素から値を収集する
    """
    from bs4 import BeautifulSoup

    results: dict = {}

    # ── iXBRL (HTML埋め込み) をBeautifulSoupで解析 ──
    soup = BeautifulSoup(content, "html.parser")

    # ix:nonFraction / ix:nonNumeric のどちらも探す
    elements = soup.find_all(lambda tag: tag.name and "nonfraction" in tag.name.lower())

    for elem in elements:
        name = elem.get("name", "")
        context = elem.get("contextref", "") or elem.get("contextRef", "")
        scale_str = elem.get("scale", "0") or "0"
        sign = elem.get("sign", "") or ""
        decimals = elem.get("decimals", "")

        text = elem.get_text(strip=True).replace(",", "").replace(" ", "").replace("\u00a0", "")
        if not text or text in ("-", "－"):
            continue

        try:
            scale = int(scale_str)
            value = float(text) * (10 ** scale)
            if sign == "-":
                value = -value
        except (ValueError, OverflowError):
            continue

        short_name = name.split(":")[-1] if ":" in name else name
        mapped = _XBRL_FIELD_MAP.get(short_name)
        if not mapped:
            continue

        # 通期・当期コンテキストを優先（連結優先）
        is_current = any(k in context for k in ("CurrentYear", "Duration", "Consolidated"))
        is_prior = any(k in context for k in ("Prior", "Previous"))

        if mapped not in results:
            results[mapped] = value
        elif is_current and not is_prior:
            results[mapped] = value

    # ── iXBRL で取れなければ通常XBRLとしてフォールバック ──
    if not results:
        results = _fallback_parse_xbrl(content)

    return results


def _fallback_parse_xbrl(content: str) -> dict:
    """通常XBRL形式のフォールバックパーサー（正規表現）"""
    import re

    results: dict = {}
    for xbrl_key, mapped_key in _XBRL_FIELD_MAP.items():
        if mapped_key in results:
            continue
        # <jppfs_cor:NetSales ...>1234567</jppfs_cor:NetSales> のようなパターン
        pattern = rf'<[^>]*:{re.escape(xbrl_key)}(?:\s[^>]*)?>([0-9,.\-]+)<'
        match = re.search(pattern, content)
        if match:
            try:
                results[mapped_key] = float(match.group(1).replace(",", ""))
            except ValueError:
                pass
    return results
