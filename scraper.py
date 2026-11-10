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
TARGET_URL = "https://www.sasabegazai.co.jp/"

def fetch_sasabe_products():
    """笹部画材のトップページや特売・新着部分から商品情報を取得する"""
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
    seen_urls = set()

    # 1. ページ内の「item.html?id=...」または「listview/item.html?id=...」のリンクをすべて探索
    links = soup.find_all('a', href=re.compile(r'item\.html\?id='))

    for link in links:
        href = link.get('href', '')
        if not href.startswith('http'):
            # 絶対パス・相対パスの調整
            product_url = BASE_URL + href.lstrip('/')
        else:
            product_url = href

        # 重複防止
        if product_url in seen_urls:
            continue
        seen_urls.add(product_url)

        # 商品名や周辺テキストの取得
        # 画像のaltや親要素・テキストから商品名を探す
        img = link.find('img')
        name = ""
        if img and img.get('alt') and img.get('alt') != "商品画像":
            name = img.get('alt').strip()
        
        if not name:
            # 周辺のテキストコンテナを探す
            container = link.find_parent(['div', 'center', 'td']) or link
            text_el = container.find('font', {'size': '2'}) or container
            name = text_el.get_text(separator=' ', strip=True)
            # 改行や余分なスペースを整理
            name = re.sub(r'\s+', ' ', name)

        if not name or len(name) < 2 or "商品画像" in name:
            continue

        # 価格の抽出（「￥1,500」や「定価￥242」などから数値を拾う）
        container_text = link.find_parent(['div', 'center', 'td']).get_text(separator=' ', strip=True) if link.find_parent(['div', 'center', 'td']) else link.get_text()
        
        price_match = re.search(r'(?:￥|\\)\s*([\d,]+)', container_text)
        price = 0
        if price_match:
            price_str = price_match.group(1).replace(',', '')
            try:
                price = int(price_str)
            except ValueError:
                price = 0

        # 在庫・セール判定
        in_stock = True
        if "品切れ" in container_text or "在庫なし" in container_text:
            in_stock = False

        products.append({
            "name": name[:100],  # 長すぎる場合は制限
            "price": price,
            "category": "画材・セール品",
            "url": product_url,
            "in_stock": in_stock
        })

    print(f"Found {len(products)} products.")
    return products

def update_supabase(products):
    """取得した商品データをSupabaseにUPSERT（更新・挿入）"""
    if not products:
        print("No products to update.")
        return

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
