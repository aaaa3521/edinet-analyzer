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
        最大180日分さかのぼって検索する
        """
        today = date.today()
        for days_back in range(0, 180):
            target = today - timedelta(days=days_back)
            try:
                docs = self.get_documents_list(target)
            except Exception:
                continue
            for doc in docs:
                if (
                    doc.get("secCode", "").startswith(securities_code)
                    and doc.get("docTypeCode") == doc_type_code
                    and doc.get("docInfoEditStatus") != "2"
                ):
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
        ZIPからXBRLを解析して財務データを抽出する
        返り値: {label: value, ...}
        """
        results = {}
        try:
            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
                # XBRL ファイルを探す（jpcrp_*_ixbrl.htm または *.xbrl）
                xbrl_files = [
                    n for n in zf.namelist()
                    if n.endswith(".xbrl") or "_ixbrl" in n
                ]
                if not xbrl_files:
                    return results

                with zf.open(xbrl_files[0]) as f:
                    content = f.read().decode("utf-8", errors="ignore")

                results = _parse_xbrl_content(content)
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


# XBRL要素名と日本語ラベルのマッピング
_XBRL_FIELD_MAP = {
    # 損益計算書
    "NetSales": "net_sales",
    "NetSalesOfCompletedConstructionContracts": "net_sales",
    "OperatingIncome": "operating_income",
    "ProfitLoss": "net_income",
    "ProfitLossAttributableToOwnersOfParent": "net_income",
    # 貸借対照表
    "Assets": "total_assets",
    "Equity": "equity",
    "NetAssets": "equity",
    "InterestBearingDebt": "interest_bearing_debt",
    "BorrowingsAndBondsPayable": "interest_bearing_debt",
    # 株式
    "EarningsPerShare": "eps",
    "NumberOfSharesOutstanding": "shares_outstanding",
}


def _parse_xbrl_content(content: str) -> dict:
    """
    XBRLコンテンツから財務数値を正規表現なしで抽出する
    簡易パーサー: タグ名をキーに数値を収集する
    """
    from xml.etree import ElementTree as ET

    results: dict = {}

    # iXBRL（HTML埋め込み）の場合はix:nonFraction要素を探す
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        # 不正XMLでも部分解析を試みる
        return _fallback_parse(content)

    ns_map = {
        "ix": "http://www.xbrl.org/2013/inlineXBRL",
        "xbrli": "http://www.xbrl.org/2003/instance",
    }

    # iXBRL形式
    for elem in root.iter():
        local = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
        if local == "nonFraction":
            name = elem.get("name", "")
            context = elem.get("contextRef", "")
            scale = int(elem.get("scale", "0") or "0")
            sign = elem.get("sign", "")
            text = (elem.text or "").strip().replace(",", "")
            if not text:
                continue
            try:
                value = float(text) * (10 ** scale)
                if sign == "-":
                    value = -value
            except ValueError:
                continue

            short_name = name.split(":")[-1] if ":" in name else name
            mapped = _XBRL_FIELD_MAP.get(short_name)
            if mapped and mapped not in results:
                # 通期コンテキストを優先
                if "CurrentYear" in context or "Duration" in context or not results.get(mapped):
                    results[mapped] = value

    # 通常XBRL形式
    if not results:
        for elem in root.iter():
            local = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            mapped = _XBRL_FIELD_MAP.get(local)
            if mapped and mapped not in results:
                text = (elem.text or "").strip().replace(",", "")
                try:
                    results[mapped] = float(text)
                except ValueError:
                    pass

    return results


def _fallback_parse(content: str) -> dict:
    """XMLパースに失敗した場合のフォールバック: 文字列検索で数値を抽出"""
    import re

    results: dict = {}
    for xbrl_key, mapped_key in _XBRL_FIELD_MAP.items():
        if mapped_key in results:
            continue
        # <jp-bs:Assets ...>12345678</jp-bs:Assets> のようなパターン
        pattern = rf'<[^>]*[:\s]{re.escape(xbrl_key)}[^>]*>([^<]+)<'
        match = re.search(pattern, content)
        if match:
            try:
                results[mapped_key] = float(match.group(1).replace(",", ""))
            except ValueError:
                pass
    return results
