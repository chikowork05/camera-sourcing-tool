#!/usr/bin/env python3
"""
仕入れハンター 自動検索スクリプト
ヤフオク・メルカリ・ラクマを検索して新着商品を通知としてindex.htmlに書き込む
"""

import json
import re
import time
import random
import hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

import requests
from bs4 import BeautifulSoup

JST = timezone(timedelta(hours=9))
NOW = datetime.now(JST)
INDEX_HTML = Path(__file__).parent / "index.html"

HEADERS_HTML = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

OK_WORDS = [
    "完動品", "完動", "動作確認済", "動作確認済み", "動作品", "動作良好", "動作OK",
    "整備済", "整備済み", "分解整備済", "美品", "良品", "極上品", "極上美品",
    "実用品", "シャッターOK", "フラッシュOK", "動作可",
]

NG_WORDS = [
    "ジャンク", "現状品", "動作未確認", "難あり", "訳あり", "一部不具合",
    "動作不良", "不動品", "不動", "通電のみ", "部品取り", "ジャンク品",
]


def gen_id(url):
    ts = NOW.strftime("%Y%m%d%H%M%S")
    h = hashlib.md5(url.encode()).hexdigest()[:6]
    return f"{ts}-{h}"


def judge(title):
    for w in NG_WORDS:
        if w in title:
            return "NG", f"NG判定: {w}"
    for w in OK_WORDS:
        if w in title:
            return "OK", f"OK判定: {w}"
    return "NG", "OKワードなし"


def make_item(cond, platform, title, url, price, img_url):
    j, reason = judge(title)
    return {
        "id": gen_id(url),
        "conditionId": cond["id"],
        "conditionName": cond["name"],
        "category": cond.get("category", "フィルムカメラ"),
        "platform": platform,
        "title": title,
        "url": url,
        "imageUrl": img_url,
        "price": price,
        "judgment": j,
        "reason": reason,
        "createdAt": NOW.isoformat(),
        "isRead": False,
        "isFavorite": False,
    }


def sleep():
    time.sleep(random.uniform(2.0, 4.0))


# ───────────────────────────────────────────
# URLからキーワード・価格上限を抽出するユーティリティ
# ───────────────────────────────────────────
def extract_keyword_from_url(url):
    """searchUrlからキーワードを抽出する"""
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    # ヤフオク: p or va
    for key in ["p", "va", "keyword"]:
        if key in qs:
            return qs[key][0]
    return ""

def extract_max_price_from_url(url):
    """searchUrlから価格上限を抽出する"""
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    for key in ["aucmaxprice", "max", "price_max"]:
        if key in qs and qs[key][0]:
            try:
                return int(qs[key][0])
            except Exception:
                pass
    return 0

def extract_category_id_from_url(url):
    """メルカリURLからcategory_idを抽出する"""
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    if "category_id" in qs:
        return qs["category_id"][0]
    return ""

def extract_exclude_keyword_from_url(url):
    """ヤフオクURLからve（除外キーワード）を抽出する"""
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    if "ve" in qs:
        return qs["ve"][0]
    return ""


# ───────────────────────────────────────────
# ヤフオク検索（HTML）
# ───────────────────────────────────────────
def search_yahoo(cond):
    url = cond["searchUrl"]
    results = []
    try:
        r = requests.get(url, headers=HEADERS_HTML, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        items = (
            soup.select("li.Product") or
            soup.select("div.Product") or
            soup.select("[class*='Product__body']") or
            soup.select("li[class*='product']")
        )

        if not items:
            links = soup.select("a[href*='page.auctions.yahoo.co.jp']")
            for a in links[:30]:
                title_text = a.get_text(strip=True)
                item_url = a.get("href", "")
                if not title_text or not item_url:
                    continue
                results.append(make_item(cond, "ヤフオク", title_text, item_url, 0, ""))
            return results

        for item in items[:30]:
            title_el = (
                item.select_one(".Product__title") or
                item.select_one("[class*='Product__title']") or
                item.select_one("h3") or item.select_one("h2")
            )
            title_text = title_el.get_text(strip=True) if title_el else ""
            a_el = item.select_one("a[href*='auctions.yahoo']") or item.select_one("a")
            item_url = a_el.get("href", "") if a_el else ""
            if not item_url.startswith("http"):
                item_url = "https://auctions.yahoo.co.jp" + item_url
            price = 0
            price_el = item.select_one(".Product__price") or item.select_one("[class*='price']")
            if price_el:
                try:
                    price = int(re.sub(r"[^\d]", "", price_el.get_text()))
                except Exception:
                    pass
            img_el = item.select_one("img")
            img_url = img_el.get("src", "") if img_el else ""
            if not title_text or not item_url:
                continue
            results.append(make_item(cond, "ヤフオク", title_text, item_url, price, img_url))

    except Exception as e:
        print(f"  [ヤフオク] {cond['name']}: エラー - {e}")
    return results


# ───────────────────────────────────────────
# メルカリ検索（非公式API）
# ───────────────────────────────────────────
def search_mercari(cond):
    results = []
    try:
        keyword = extract_keyword_from_url(cond["searchUrl"])
        price_max = extract_max_price_from_url(cond["searchUrl"])
        category_id = extract_category_id_from_url(cond["searchUrl"])

        if not keyword:
            print(f"  [メルカリ] {cond['name']}: キーワード抽出失敗")
            return results

        # メルカリ非公式API
        api_url = "https://api.mercari.jp/v2/entities:search"
        payload = {
            "pageSize": 30,
            "searchSessionId": gen_id(keyword),
            "indexRouting": "INDEX_ROUTING_UNSPECIFIED",
            "thumbnailTypes": [],
            "searchCondition": {
                "keyword": keyword,
                "excludeKeyword": "",
                "sort": "SORT_CREATED_TIME",
                "order": "ORDER_DESC",
                "status": ["STATUS_ON_SALE"],
                "categoryId": [category_id] if category_id else [],
                "brandId": [],
                "sellerId": [],
                "priceMin": 0,
                "priceMax": price_max if price_max else 0,
                "itemConditionId": [],
                "shippingPayerId": [],
                "shippingFromArea": [],
                "shippingMethod": [],
                "colorId": [],
                "hasCoupon": False,
                "attributes": [],
                "itemTypes": [],
                "skuIds": [],
            },
            "defaultDatasets": ["DATASET_TYPE_MERCARI", "DATASET_TYPE_BEYOND"],
            "serviceFrom": "suruga",
            "userId": "",
            "withItemBrand": True,
            "withItemSize": False,
            "withItemPromotions": False,
            "withItemSizes": False,
            "withShopname": False,
        }
        headers = {
            **HEADERS_HTML,
            "Content-Type": "application/json",
            "X-Platform": "web",
            "Accept": "application/json",
            "DPoP": "dummy",
        }
        r = requests.post(api_url, json=payload, headers=headers, timeout=20)
        r.raise_for_status()
        data = r.json()

        items = data.get("items", [])
        for item in items:
            title_text = item.get("name", "")
            item_id = item.get("id", "")
            item_url = f"https://jp.mercari.com/item/{item_id}" if item_id else ""
            try:
                price = int(item.get("price", 0))
            except Exception:
                price = 0
            thumbnails = item.get("thumbnails", [])
            img_url = thumbnails[0] if thumbnails else ""
            if not title_text or not item_url:
                continue
            results.append(make_item(cond, "メルカリ", title_text, item_url, price, img_url))

    except Exception as e:
        print(f"  [メルカリ] {cond['name']}: エラー - {e}")
    return results


# ───────────────────────────────────────────
# ラクマ検索（非公式API）
# ───────────────────────────────────────────
def search_rakuma(cond):
    results = []
    try:
        keyword = extract_keyword_from_url(cond["searchUrl"]) or cond["name"]
        price_max = extract_max_price_from_url(cond["searchUrl"])

        api_url = "https://api.fril.jp/v1/items"
        params = {
            "keyword": keyword,
            "limit": 30,
            "sort": "created_at",
            "order": "desc",
            "status": "on_sale",
        }
        if price_max:
            params["price_to"] = price_max

        headers = {
            **HEADERS_HTML,
            "Accept": "application/json",
        }
        r = requests.get(api_url, params=params, headers=headers, timeout=20)
        r.raise_for_status()
        data = r.json()

        items = data.get("items", [])
        for item in items:
            title_text = item.get("name", "")
            item_id = item.get("id", "")
            item_url = f"https://fril.jp/items/{item_id}" if item_id else ""
            try:
                price = int(item.get("price", 0))
            except Exception:
                price = 0
            img_url = item.get("image_url", "") or item.get("images", [{}])[0].get("url", "")
            if not title_text or not item_url:
                continue
            results.append(make_item(cond, "ラクマ", title_text, item_url, price, img_url))

    except Exception as e:
        print(f"  [ラクマ] {cond['name']}: エラー - {e}")
    return results


# ───────────────────────────────────────────
# index.html 読み書き
# ───────────────────────────────────────────
def load_index_html():
    html = INDEX_HTML.read_text(encoding="utf-8")
    m = re.search(
        r'(<script id="embedded-data" type="application/json">)(.*?)(</script>)',
        html, re.DOTALL
    )
    if not m:
        raise ValueError("embedded-data が見つかりません")
    raw = m.group(2)
    cleaned = re.sub(
        r'(?<!\\)[\x00-\x1f]',
        lambda c: "\\u{:04x}".format(ord(c.group())),
        raw
    )
    data = json.loads(cleaned)
    return html, data


def save_index_html(html, data):
    json_str = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    new_html = re.sub(
        r'(<script id="embedded-data" type="application/json">)(.*?)(</script>)',
        lambda m: m.group(1) + json_str + m.group(3),
        html, flags=re.DOTALL
    )
    INDEX_HTML.write_text(new_html, encoding="utf-8")
    print("index.html を更新しました")


# ───────────────────────────────────────────
# メイン
# ───────────────────────────────────────────
def main():
    print(f"=== 仕入れハンター 自動検索 開始 {NOW.strftime('%Y-%m-%d %H:%M JST')} ===")

    html, data = load_index_html()
    search_conditions = data.get("searchConditions", [])
    existing_notis = data.get("notifications", [])
    existing_urls = {n.get("url", "") for n in existing_notis}

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
        elif platform == "ラクマ":
            results = search_rakuma(cond)
        else:
            results = []

        added = 0
        for r in results:
            if r["url"] and r["url"] not in existing_urls:
                new_notis.append(r)
                existing_urls.add(r["url"])
                added += 1

        ok_count = sum(1 for r in results if r["judgment"] == "OK")
        print(f"  → {len(results)}件取得, OK: {ok_count}件, 新規追加: {added}件")

        sleep()

    print(f"\n新着通知合計: {len(new_notis)}件")

    merged = new_notis + existing_notis
    merged = merged[:1000]

    data["notifications"] = merged
    data["lastUpdated"] = NOW.isoformat()

    save_index_html(html, data)
    print("=== 完了 ===")


if __name__ == "__main__":
    main()
