"""笹部洋画材料店 商品スクレイパー (v2.1)

- 笹部画材（sasabegazai.co.jp）の全ブランド・シリーズ一覧（244シリーズ）を巡回
- 実商品と実売価格・定価を抽出し、Supabase の products テーブルへ一括 Upsert
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


def money(text):
    m = re.search(r"[￥\\]\s*([\d,]+)", text or "")
    return int(m.group(1).replace(",", "")) if m else None


def series_links(session):
    """トップページのサイドバーから「シリーズ（ブランド）ページ」のIDを集める。"""
    try:
        resp = session.get(BASE_URL, timeout=20)
        if resp.status_code != 200:
            print(f"Failed to fetch top page: HTTP {resp.status_code}", flush=True)
            return {}
        html = resp.content.decode("utf-8", "replace")
        soup = BeautifulSoup(html, "html.parser")
        out = {}
        for a in soup.select("#sideNav .midCategoryBtn a"):
            m = re.search(r"id=(\d+)", a.get("href", ""))
            if m:
                out[m.group(1)] = a.get_text(" ", strip=True).strip()
        return out
    except Exception as e:
        print(f"Error fetching series links: {e}", flush=True)
        return {}


def product_id(row):
    sel = row.select_one('select[name^="id_"]')
    if sel:
        return sel["name"][3:]
    a = row.select_one('a.popup[href*="id="]')
    if a:
        m = re.search(r"id=(\d+)", a["href"])
        if m:
            return m.group(1)
    return ""


def parse(html):
    soup = BeautifulSoup(html, "html.parser")
    products = []

    for blk in soup.select("table.dpItemTable"):
        title_el = blk.select_one("h2")
        series = title_el.get_text(" ", strip=True) if title_el else ""
        sizes = [td.get_text(" ", strip=True) for td in blk.select("tr td.item-001")]

        # --- A) 色×サイズの表 ---
        for tr in blk.select("tr"):
            namecell = tr.select_one("td table.dpSizeTableName")
            if not namecell:
                continue
            color_el = namecell.select_one("td.item-003 a") or namecell.select_one("td.item-003")
            color = color_el.get_text(" ", strip=True) if color_el else ""
            cells = [td for td in tr.find_all("td", recursive=False) if not td.find("table")]
            for i, td in enumerate(cells):
                p5 = td.select_one("p.item-005")
                p4 = td.select_one("p.item-004")
                price = money(p5.get_text()) if p5 else None
                if not price:
                    continue
                pid = product_id(td)
                size = sizes[i] if i < len(sizes) else ""
                name = " ".join(x for x in (series, color, size) if x)
                products.append(
                    {
                        "name": name[:200],
                        "price": price,
                        "url": f"{BASE_URL}pop.html?id={pid}" if pid else f"{BASE_URL}item_{pid}",
                    }
                )

        # --- B) 1商品1行 ---
        for tr in blk.select("tr"):
            p10 = tr.select_one("p.item-010")
            if not p10:
                continue
            price = money(p10.get_text())
            if not price:
                continue
            pid = product_id(tr)
            if not pid:
                continue
            products.append(
                {
                    "name": series[:200],
                    "price": price,
                    "url": f"{BASE_URL}pop.html?id={pid}",
                }
            )

    # url 重複を落とす
    seen, unique = set(), []
    for p in products:
        if p["url"] in seen:
            continue
        seen.add(p["url"])
        unique.append(p)
    return unique


def crawl(session, only=None):
    series = series_links(session)
    print(f"Found {len(series)} series pages to crawl.", flush=True)
    all_items, failed = [], []
    for n, (sid, label) in enumerate(sorted(series.items()), 1):
        if only and sid not in only:
            continue
        url = f"{BASE_URL}listview/item.html?id={sid}"
        try:
            r = session.get(url, timeout=40)
            if r.status_code != 200:
                failed.append((sid, label, f"HTTP {r.status_code}"))
                continue
            items = parse(r.content.decode("utf-8", "replace"))
            for it in items:
                it["category"] = label
                it["in_stock"] = True
            all_items.extend(items)
            print(f"[{n}/{len(series)}] {sid} {label}: {len(items)} items", flush=True)
        except Exception as e:
            failed.append((sid, label, repr(e)))
        time.sleep(SLEEP)

    if failed:
        print(f"FAILED pages ({len(failed)}):", flush=True)
        for f in failed[:20]:
            print("  ", f, flush=True)
    return all_items, failed


def update_supabase(items):
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_KEY")
    if not supabase_url or not supabase_key:
        print("ERROR: SUPABASE_URL と SUPABASE_KEY の環境変数が設定されていません。", flush=True)
        return False

    if os.environ.get("DRY_RUN"):
        print("DRY_RUN mode enabled: skipping Supabase write.", flush=True)
        return True

    supabase: Client = create_client(supabase_url, supabase_key)
    rows = []
    for it in items:
        rows.append({
            "name": it["name"],
            "price": it["price"],
            "category": it.get("category", "画材"),
            "url": it["url"],
            "in_stock": it.get("in_stock", True),
        })

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
            # UNIQUE制約エラー等の場合は無駄な1件リトライをせず即座に中断
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
