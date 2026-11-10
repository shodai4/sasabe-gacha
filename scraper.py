"""笹部洋画材料店 商品スクレイパー (v3.1)

- 笹部画材（sasabegazai.co.jp）の全ブランド・シリーズ一覧（244シリーズ）を巡回
- サイトトップの第1階層大カテゴリー（油絵具・ピグメント等）を抽出し商品に紐付け
- 特設「オリジナル商品」ページ（original.html）も巡回し、全16カテゴリー網羅
- 実商品と実売価格を抽出し、Supabase の products テーブルへ一括 Upsert
- サーバー負荷軽減のため 0.5s 待機、0件時は安全停止
"""
import os
import re
import sys
import time
import requests
from bs4 import BeautifulSoup
from supabase import Client, create_client

BASE_URL = "https://www.sasabegazai.co.jp/"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}

# サーバー負荷軽減のための待機時間（秒）
SLEEP = 0.5


def parse_money(text):
    """¥や￥付きの金額文字列から数値を抽出"""
    m = re.search(r"[￥\\]\s*([\d,]+)", text or "")
    return int(m.group(1).replace(",", "")) if m else None


def fetch_series_and_categories(session):
    """トップページのサイドバーから「大カテゴリー名」と「シリーズID・シリーズ名」を取得する。

    戻り値:
        dict: {
            "1101": {"category": "油絵具・ピグメント", "series": "【国産】 クサカベ"},
            ...
        }
    """
    try:
        resp = session.get(BASE_URL, timeout=20)
        if resp.status_code != 200:
            print(f"Failed to fetch top page: HTTP {resp.status_code}", flush=True)
            return {}

        html = resp.content.decode("utf-8", "replace")
        soup = BeautifulSoup(html, "html.parser")
        out = {}

        # 1. BeautifulSoup による DOM 走査
        for li in soup.select("#sideNav ul.categoryBtn > li"):
            main_a = li.select_one("a.categoryBtn")
            if not main_a:
                continue
            span = main_a.select_one("span")
            main_cat = span.get_text(strip=True) if span else main_a.get_text(strip=True)
            main_cat = re.sub(r"\s+", " ", main_cat).strip()

            for mid_a in li.select("ul.midCategoryBtn a"):
                m = re.search(r"id=(\d+)", mid_a.get("href", ""))
                if m:
                    sid = m.group(1)
                    sname = re.sub(r"\s+", " ", mid_a.get_text(" ", strip=True)).strip()
                    out[sid] = {
                        "category": main_cat,
                        "series": sname,
                    }

        # 2. 念のための正規表現フォールバック（マークアップ微差用）
        if len(out) < 200:
            print(f"Warning: BeautifulSoup found only {len(out)} series. Running regex fallback...", flush=True)
            pattern = re.compile(
                r"<a href=\"category\.html\?id=\d+\"[^>]*>.*?<span>(.*?)</span>.*?<ul class=\"midCategoryBtn\"[^>]*>(.*?)</ul>",
                re.DOTALL
            )
            matches = pattern.findall(html)
            for cat_name, mid_html in matches:
                cat = re.sub(r"\s+", " ", cat_name).strip()
                for sid, sname in re.findall(r"href=\"item\.html\?id=(\d+)\">([^<]+)</a>", mid_html):
                    if sid not in out:
                        out[sid] = {
                            "category": cat,
                            "series": re.sub(r"\s+", " ", sname).strip(),
                        }

        return out
    except Exception as e:
        print(f"Error fetching series links: {e}", flush=True)
        return {}


def extract_product_id(element):
    """HTML要素から商品ID（ポップアップ用）を抽出"""
    sel = element.select_one('select[name^="id_"]')
    if sel:
        return sel["name"][3:]
    a = element.select_one('a.popup[href*="id="]')
    if a:
        m = re.search(r"id=(\d+)", a["href"])
        if m:
            return m.group(1)
    return ""


def parse_item_page(html):
    """シリーズ詳細ページから個別商品の一覧を抽出"""
    soup = BeautifulSoup(html, "html.parser")
    products = []

    for blk in soup.select("table.dpItemTable"):
        title_el = blk.select_one("h2")
        series = title_el.get_text(" ", strip=True) if title_el else ""
        sizes = [td.get_text(" ", strip=True) for td in blk.select("tr td.item-001")]

        # パターンA: 色 × サイズの表形式
        for tr in blk.select("tr"):
            namecell = tr.select_one("td table.dpSizeTableName")
            if not namecell:
                continue
            color_el = namecell.select_one("td.item-003 a") or namecell.select_one("td.item-003")
            color = color_el.get_text(" ", strip=True) if color_el else ""
            cells = [td for td in tr.find_all("td", recursive=False) if not td.find("table")]

            for i, td in enumerate(cells):
                p5 = td.select_one("p.item-005")  # 実売価格
                price = parse_money(p5.get_text()) if p5 else None
                if not price:
                    continue
                pid = extract_product_id(td)
                size = sizes[i] if i < len(sizes) else ""
                name = " ".join(x for x in (series, color, size) if x)
                products.append({
                    "name": name[:200],
                    "price": price,
                    "url": f"{BASE_URL}pop.html?id={pid}" if pid else f"{BASE_URL}item_{pid}",
                })

        # パターンB: 1商品1行のリスト形式
        for tr in blk.select("tr"):
            p10 = tr.select_one("p.item-010")  # 実売価格
            if not p10:
                continue
            price = parse_money(p10.get_text())
            if not price:
                continue
            pid = extract_product_id(tr)
            if not pid:
                continue
            products.append({
                "name": series[:200],
                "price": price,
                "url": f"{BASE_URL}pop.html?id={pid}",
            })

    # URL単位での重複除外
    seen = set()
    unique = []
    for p in products:
        if p["url"] in seen:
            continue
        seen.add(p["url"])
        unique.append(p)
    return unique


def crawl_original_products(session):
    """笹部画材オリジナル商品特設ページ（original.html）からオリジナル商品一覧を取得"""
    url = f"{BASE_URL}original.html"
    try:
        r = session.get(url, timeout=30)
        if r.status_code != 200:
            print(f"Failed to fetch original products page: HTTP {r.status_code}", flush=True)
            return []

        html = r.content.decode("utf-8", "replace")
        soup = BeautifulSoup(html, "html.parser")
        items = []

        for card in soup.select("div.product-card"):
            h3 = card.select_one("h3")
            p_price = card.select_one("p.price")
            a_link = card.select_one("a.btn-detail") or card.select_one('a[href*="pop.html"], a[href*="item.html"]')

            if not (h3 and p_price and a_link):
                continue

            name = h3.get_text(" ", strip=True)
            name = re.sub(r"\s+", " ", name).strip()
            price = parse_money(p_price.get_text())
            if not price:
                continue

            href = a_link.get("href", "").strip()
            if not href.startswith("http"):
                href = BASE_URL + href.lstrip("/")

            items.append({
                "name": name[:200],
                "price": price,
                "category": "オリジナル商品",
                "url": href,
                "in_stock": True,
            })

        seen = set()
        unique = []
        for it in items:
            if it["url"] in seen:
                continue
            seen.add(it["url"])
            unique.append(it)

        print(f"[オリジナル商品] Fetched {len(unique)} original products from original.html", flush=True)
        return unique
    except Exception as e:
        print(f"Error crawling original products: {e}", flush=True)
        return []


def crawl(session, only_series_ids=None):
    """全シリーズおよびオリジナル商品ページを巡回して商品リストを収集"""
    series_map = fetch_series_and_categories(session)
    print(f"Found {len(series_map)} series pages across categories to crawl.", flush=True)

    all_items = []
    failed = []

    for n, (sid, info) in enumerate(sorted(series_map.items()), 1):
        if only_series_ids and sid not in only_series_ids:
            continue

        cat = info["category"]
        sname = info["series"]
        url = f"{BASE_URL}listview/item.html?id={sid}"

        try:
            r = session.get(url, timeout=40)
            if r.status_code != 200:
                failed.append((sid, f"[{cat}] {sname}", f"HTTP {r.status_code}"))
                continue

            items = parse_item_page(r.content.decode("utf-8", "replace"))
            for it in items:
                it["category"] = cat
                it["in_stock"] = True

            all_items.extend(items)
            print(f"[{n}/{len(series_map)}] {sid} [{cat}] {sname}: {len(items)} items", flush=True)
        except Exception as e:
            failed.append((sid, f"[{cat}] {sname}", repr(e)))

        time.sleep(SLEEP)

    # オリジナル商品特設ページの巡回
    orig_items = crawl_original_products(session)
    if orig_items:
        all_items.extend(orig_items)

    if failed:
        print(f"FAILED pages ({len(failed)}):", flush=True)
        for f in failed[:20]:
            print("  ", f, flush=True)

    return all_items, failed


def update_supabase(items):
    """Supabase の products テーブルへ一括 Upsert"""
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_KEY")
    if not supabase_url or not supabase_key:
        print("ERROR: SUPABASE_URL と SUPABASE_KEY の環境変数が設定されていません。", flush=True)
        return False

    if os.environ.get("DRY_RUN"):
        print("DRY_RUN mode enabled: skipping Supabase write.", flush=True)
        return True

    supabase: Client = create_client(supabase_url, supabase_key)
    rows = [
        {
            "name": it["name"],
            "price": it["price"],
            "category": it.get("category", "画材"),
            "url": it["url"],
            "in_stock": it.get("in_stock", True),
        }
        for it in items
    ]

    print(f"Upserting {len(rows)} products to Supabase...", flush=True)
    CHUNK_SIZE = 100
    success_count = 0
    error_count = 0

    for i in range(0, len(rows), CHUNK_SIZE):
        chunk = rows[i:i + CHUNK_SIZE]
        try:
            supabase.table("products").upsert(chunk, on_conflict="url").execute()
            success_count += len(chunk)
            if (i // CHUNK_SIZE) % 10 == 0:
                print(f"Progress: {success_count}/{len(rows)} upserted...", flush=True)
        except Exception as e:
            error_count += len(chunk)
            print(f"Error upserting chunk {i}~{i+len(chunk)}: {e}", flush=True)
            if "there is no unique or exclusion constraint" in str(e):
                print("\n[CRITICAL] Supabaseの products テーブルの url 列に UNIQUE 制約が必要です！", flush=True)
                print("Supabase SQL Editorで以下を実行してください:", flush=True)
                print("  ALTER TABLE products ADD CONSTRAINT products_url_unique UNIQUE (url);\n", flush=True)
                return False

    print(f"Completed: {success_count} succeeded, {error_count} failed out of {len(rows)} products.", flush=True)
    return success_count > 0 and error_count == 0


def main():
    only = set(sys.argv[1:]) or None
    session = requests.Session()
    session.headers.update(HEADERS)

    start_time = time.time()
    items, failed = crawl(session, only)
    elapsed = time.time() - start_time
    print(f"Total products parsed: {len(items)} (Crawl time: {elapsed:.1f}s)", flush=True)

    if not items:
        print("No products parsed — aborting without touching Supabase.", flush=True)
        return 1

    suspicious = sum(1 for i in items if not i.get("price"))
    if suspicious:
        print(f"Warning: {suspicious} products without valid price.", flush=True)

    success = update_supabase(items)
    return 0 if success else 2


if __name__ == "__main__":
    sys.exit(main())
