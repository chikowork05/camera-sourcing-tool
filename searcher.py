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
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup

JST = timezone(timedelta(hours=9))
NOW = datetime.now(JST)
INDEX_HTML = Path(__file__).parent / "index.html"

HEADERS = {
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


def sleep():
    time.sleep(random.uniform(2.0, 4.0))


# ───────────────────────────────────────────
# ヤフオク検索（HTML）
# ───────────────────────────────────────────
def search_yahoo(cond):
    url = cond["searchUrl"]
    results = []
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        # 商品リストを取得（複数のセレクタを試す）
        items = (
            soup.select("li.Product") or
            soup.select("div.Product") or
            soup.select("[class*='Product__body']") or
            soup.select("li[class*='product']")
        )

        # セレクタで取れない場合はaタグから直接探す
        if not items:
            links = soup.select("a[href*='page.auctions.yahoo.co.jp']")
            for a in links[:30]:
                title_text = a.get_text(strip=True)
                item_url = a.get("href", "")
                if not title_text or not item_url:
                    continue
                j, reason = judge(title_text)
                results.append({
                    "id": gen_id(item_url),
                    "conditionId": cond["id"],
                    "conditionName": cond["name"],
                    "category": cond.get("category", "フィルムカメラ"),
                    "platform": "ヤフオク",
                    "title": title_text,
                    "url": item_url,
                    "imageUrl": "",
                    "price": 0,
                    "judgment": j,
                    "reason": reason,
                    "createdAt": NOW.isoformat(),
                    "isRead": False,
                    "isFavorite": False,
                })
            return results

        for item in items[:30]:
            # タイトル取得
            title_el = (
                item.select_one(".Product__title") or
                item.select_one("[class*='Product__title']") or
                item.select_one("h3") or
                item.select_one("h2")
            )
            title_text = title_el.get_text(strip=True) if title_el else ""

            # URL取得
            a_el = item.select_one("a[href*='auctions.yahoo']") or item.select_one("a")
            item_url = a_el.get("href", "") if a_el else ""
            if not item_url.startswith("http"):
                item_url = "https://auctions.yahoo.co.jp" + item_url

            # 価格取得
            price = 0
            price_el = item.select_one(".Product__price") or item.select_one("[class*='price']")
            if price_el:
                try:
                    price = int(re.sub(r"[^\d]", "", price_el.get_text()))
                except Exception:
                    pass

            # 画像取得
            img_el = item.select_one("img")
            img_url = img_el.get("src", "") if img_el else ""

            if not title_text or not item_url:
                continue

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
# メルカリ検索（HTML）
# ───────────────────────────────────────────
def search_mercari(cond):
    url = cond["searchUrl"]
    results = []
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        # JSON-LDから取得を試みる
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if item.get("@type") != "Product":
                        continue
                    title_text = item.get("name", "")
                    item_url = item.get("url", "")
                    try:
                        price = int(item.get("offers", {}).get("price", 0))
                    except Exception:
                        price = 0
                    img_url = item.get("image", "")
                    if isinstance(img_url, list):
                        img_url = img_url[0] if img_url else ""
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
            except Exception:
                pass

        # JSON-LDで取れなければHTMLから
        if not results:
            for item in soup.select("li[data-testid='item-cell'], [class*='items__item']")[:30]:
                a_el = item.select_one("a")
                if not a_el:
                    continue
                title_text = a_el.get("aria-label", "") or a_el.get_text(strip=True)
                href = a_el.get("href", "")
                item_url = href if href.startswith("http") else "https://jp.mercari.com" + href
                img_el = item.select_one("img")
                img_url = img_el.get("src", "") if img_el else ""
                price = 0
                price_el = item.select_one("[class*='price']")
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
