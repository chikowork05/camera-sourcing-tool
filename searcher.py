#!/usr/bin/env python3
"""
仕入れハンター 自動検索スクリプト
ヤフオク・メルカリを検索して新着商品を通知としてindex.htmlに書き込む
"""

import json
import re
import time
import random
import hashlib
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ───────────────────────────────────────────
# 設定
# ───────────────────────────────────────────
JST = timezone(timedelta(hours=9))
NOW = datetime.now(JST)
INDEX_HTML = Path(__file__).parent/ "index.html"

HEADERS_BASE = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}

# OK判定キーワード（タイトルに含まれていればOK）
OK_WORDS = [
    "完動品", "完動", "動作確認済", "動作確認済み", "動作品", "動作良好", "動作OK",
    "整備済", "整備済み", "分解整備済", "美品", "良品", "極上品", "極上美品",
    "実用品", "シャッターOK", "フラッシュOK", "動作可",
]

# NG判定キーワード（タイトルに含まれていればNG）
NG_WORDS = [
    "ジャンク", "現状品", "動作未確認", "難あり", "訳あり", "一部不具合",
    "動作不良", "不動品", "不動", "通電のみ", "部品取り", "ジャンク品",
]


# ───────────────────────────────────────────
# ユーティリティ
# ───────────────────────────────────────────
def gen_id(url: str) -> str:
    ts = NOW.strftime("%Y%m%d%H%M%S")
    h = hashlib.md5(url.encode()).hexdigest()[:6]
    return f"{ts}-{h}"


def judge(title: str) -> tuple[str, str]:
    """タイトルからOK/NGを判定してreason文字列も返す"""
    for w in NG_WORDS:
        if w in title:
            return "NG", f"NG判定: {w}"
    for w in OK_WORDS:
        if w in title:
            return "OK", f"OK判定: {w}"
    return "NG", "OKワードなし"


def sleep():
    time.sleep(random.uniform(1.5, 3.5))


# ───────────────────────────────────────────
# ヤフオク検索
# ───────────────────────────────────────────
def search_yahoo(cond: dict) -> list[dict]:
    url = cond["searchUrl"]
    results = []
    try:
        # RSSフィードで取得（HTMLよりも安定）
        rss_url = url.replace(
            "auctions.yahoo.co.jp/search/search",
            "auctions.yahoo.co.jp/rss/search"
        )
        r = requests.get(rss_url, headers=HEADERS_BASE, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.content, "xml")
        items = soup.find_all("item")
        for item in items[:30]:  # 最大30件
            title = item.find("title")
            link  = item.find("link")
            price_tag = item.find("price")  # ヤフオクRSSはYahoo独自タグを持つ場合あり
            if not title or not link:
                continue
            title_text = title.get_text(strip=True)
            item_url   = link.get_text(strip=True)
            # 価格を取得（色々な場所にある）
            price = 0
            for tag_name in ["price", "currentPrice", "auc:currentPrice"]:
                t = item.find(tag_name)
                if t:
                    try:
                        price = int(re.sub(r"[^\d]", "", t.get_text()))
                        break
                    except Exception:
                        pass
            # 画像
            img_url = ""
            for tag_name in ["enclosure", "media:thumbnail", "media:content"]:
                t = item.find(tag_name)
                if t:
                    img_url = t.get("url", "")
                    break

            j, reason = judge(title_text)
            results.append({
                "id": gen_id(item_url),
                "conditionId": cond["id"],
                "conditionName": cond["name"],
                "category": cond.get("category", "フィルムカメラ"),
                "platform": "ヤフオク",
                "title": title_text,
                "url": item_url,
                "imageUrl": img_url,
                "price": price,
                "judgment": j,
                "reason": reason,
                "createdAt": NOW.isoformat(),
                "isRead": False,
                "isFavorite": False,
            })
    except Exception as e:
        print(f"  [ヤフオク] {cond['name']}: エラー - {e}")
    return results


# ───────────────────────────────────────────
# メルカリ検索
# ───────────────────────────────────────────
def search_mercari(cond: dict) -> list[dict]:
    url = cond["searchUrl"]
    results = []
    try:
        headers = {**HEADERS_BASE, "Accept": "text/html,application/xhtml+xml"}
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        # メルカリのJSON-LDや埋め込みデータから商品情報を取得
        scripts = soup.find_all("script", type="application/ld+json")
        for script in scripts:
            try:
                data = json.loads(script.string or "")
                if isinstance(data, list):
                    for item in data:
                        if item.get("@type") == "Product":
                            title_text = item.get("name", "")
                            item_url   = item.get("url", "")
                            price      = int(item.get("offers", {}).get("price", 0))
                            img_url    = item.get("image", "")
                            if isinstance(img_url, list):
                                img_url = img_url[0] if img_url else ""
                            j, reason = judge(title_text)
                            results.append({
                                "id": gen_id(item_url),
                                "conditionId": cond["id"],
                                "conditionName": cond["name"],
                                "category": cond.get("category", "フィルムカメラ"),
                                "platform": "メルカリ",
                                "title": title_text,
                                "url": item_url,
                                "imageUrl": img_url,
                                "price": price,
                                "judgment": j,
                                "reason": reason,
                                "createdAt": NOW.isoformat(),
                                "isRead": False,
                                "isFavorite": False,
                            })
            except Exception:
                pass

        # JSON-LDで取れない場合はHTMLから直接パース
        if not results:
            items = soup.select("li[data-testid='item-cell'], div[data-item-id]")
            for item in items[:30]:
                a_tag = item.select_one("a")
                if not a_tag:
                    continue
                title_text = a_tag.get("aria-label", "") or a_tag.get_text(strip=True)
                item_url   = "https://jp.mercari.com" + a_tag.get("href", "")
                img        = item.select_one("img")
                img_url    = img.get("src", "") if img else ""
                price_el   = item.select_one("[class*='price'], [data-testid='price']")
                price      = 0
                if price_el:
                    try:
                        price = int(re.sub(r"[^\d]", "", price_el.get_text()))
                    except Exception:
                        pass
                if not title_text:
                    continue
                j, reason = judge(title_text)
                results.append({
                    "id": gen_id(item_url),
                    "conditionId": cond["id"],
                    "conditionName": cond["name"],
                    "category": cond.get("category", "フィルムカメラ"),
                    "platform": "メルカリ",
                    "title": title_text,
                    "url": item_url,
                    "imageUrl": img_url,
                    "price": price,
                    "judgment": j,
                    "reason": reason,
                    "createdAt": NOW.isoformat(),
                    "isRead": False,
                    "isFavorite": False,
                })
    except Exception as e:
        print(f"  [メルカリ] {cond['name']}: エラー - {e}")
    return results


# ───────────────────────────────────────────
# index.html の読み書き
# ───────────────────────────────────────────
def load_index_html() -> tuple[str, dict]:
    html = INDEX_HTML.read_text(encoding="utf-8")
    m = re.search(
        r'(<script id="embedded-data" type="application/json">)(.*?)(</script>)',
        html, re.DOTALL
    )
    if not m:
        raise ValueError("embedded-data が見つかりません")
    raw = m.group(2)
    # 制御文字をエスケープしてパース
    cleaned = re.sub(
        r'(?<!\\)[\x00-\x1f]',
        lambda c: "\\u{:04x}".format(ord(c.group())),
        raw
    )
    data = json.loads(cleaned)
    return html, data


def save_index_html(html: str, data: dict):
    # JSON文字列を生成（criteriaの改行は \n として保存）
    json_str = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    # embedded-data を置換
    new_html = re.sub(
        r'(<script id="embedded-data" type="application/json">)(.*?)(</script>)',
        lambda m: m.group(1) + json_str + m.group(3),
        html, flags=re.DOTALL
    )
    INDEX_HTML.write_text(new_html, encoding="utf-8")
    print(f"index.html を更新しました")


# ───────────────────────────────────────────
# メイン処理
# ───────────────────────────────────────────
def main():
    print(f"=== 仕入れハンター 自動検索 開始 {NOW.strftime('%Y-%m-%d %H:%M JST')} ===")

    # index.html を読み込む
    html, data = load_index_html()
    search_conditions = data.get("searchConditions", [])
    existing_notis = data.get("notifications", [])
    existing_ids = {n["id"] for n in existing_notis}

    # 有効な条件だけ対象
    active_conds = [c for c in search_conditions if c.get("enabled", True)]
    print(f"検索条件: {len(active_conds)}件 (全{len(search_conditions)}件中)")

    new_notis = []
    for i, cond in enumerate(active_conds):
        platform = cond.get("platform", "ヤフオク")
        print(f"[{i+1}/{len(active_conds)}] {platform} - {cond['name']} を検索中...")

        if platform == "ヤフオク":
            results = search_yahoo(cond)
        elif platform == "メルカリ":
            results = search_mercari(cond)
        else:
            results = []

        # URLベースの重複チェック（既存IDとURLの両方で確認）
        existing_urls = {n.get("url", "") for n in existing_notis}
        for r in results:
            if r["id"] not in existing_ids and r["url"] not in existing_urls:
                new_notis.append(r)
                existing_ids.add(r["id"])
                existing_urls.add(r["url"])

        ok_count = sum(1 for r in results if r["judgment"] == "OK")
        print(f"  → {len(results)}件取得, OK: {ok_count}件, 新規: {sum(1 for r in results if r['url'] not in existing_urls)}件")

        sleep()

    print(f"\n新着通知: {len(new_notis)}件")

    # 新着を先頭に追加（古い通知は最大1000件まで保持）
    merged = new_notis + existing_notis
    merged = merged[:1000]

    data["notifications"] = merged
    data["lastUpdated"] = NOW.isoformat()

    save_index_html(html, data)
    print(f"=== 完了 ===")


if __name__ == "__main__":
    main()
