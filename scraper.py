import os
import re
import requests
from bs4 import BeautifulSoup
from supabase import create_client, Client

# 環境変数からSupabaseの接続情報を取得
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("SUPABASE_URL と SUPABASE_KEY の環境変数が設定されていません。")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

BASE_URL = "https://www.sasabegazai.co.jp/"
# 笹部画材の商品一覧ページ
TARGET_URL = "https://www.sasabegazai.co.jp/item.html"

def fetch_sasabe_products():
    """笹部画材のサイトから商品情報を取得してリストで返す"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        response = requests.get(TARGET_URL, headers=headers, timeout=15)
        response.encoding = response.apparent_encoding or 'utf-8'
    except Exception as e:
        print(f"Failed to connect: {e}")
        return []

    if response.status_code != 200:
        print(f"Failed to fetch page: {response.status_code}")
        return []

    soup = BeautifulSoup(response.text, 'html.parser')
    products = []

    # 商品リンク (item.html?id=...) または商品要素を探す
    links = soup.find_all('a', href=re.compile(r'item\.html\?id='))
    
    seen_urls = set()

    for link in links:
        product_url = link.get('href', '')
        if not product_url.startswith('http'):
            product_url = BASE_URL + product_url.lstrip('/')

        # 重複チェック
        if product_url in seen_urls:
            continue
        seen_urls.add(product_url)

        # 親要素や周辺テキストから商品名や価格を取得
        container = link.find_parent(['td', 'div', 'li', 'tr']) or link
        text_content = container.get_text(separator=' ', strip=True)

        name = link.get_text(strip=True)
        if not name or len(name) < 2:
            continue

        # 価格（数字）の抽出
        price_match = re.search(r'(\d{1,3}(?:,\d{3})*|\d+)\s*円', text_content)
        price = 0
        if price_match:
            price_str = price_match.group(1).replace(',', '')
            try:
                price = int(price_str)
            except ValueError:
                price = 0

        # 在庫判定
        in_stock = True
        if "品切れ" in text_content or "在庫なし" in text_content:
            in_stock = False

        products.append({
            "name": name,
            "price": price,
            "category": "画材",
            "url": product_url,
            "in_stock": in_stock
        })

    print(f"Found {len(products)} products.")
    return products

def update_supabase(products):
    """取得した商品データをSupabaseにUPSERT（更新・挿入）"""
    success_count = 0
    for item in products:
        try:
            supabase.table('products').upsert(
                item, on_conflict='url'
            ).execute()
            success_count += 1
        except Exception as e:
            print(f"Error upserting {item.get('name')}: {e}")
            
    print(f"Successfully updated {success_count} products in Supabase.")

if __name__ == "__main__":
    items = fetch_sasabe_products()
    if items:
        update_supabase(items)
    else:
        print("No products found.")
