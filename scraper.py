import os
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
TARGET_URL = "https://www.sasabegazai.co.jp/products/list"

def fetch_sasabe_products():
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    response = requests.get(TARGET_URL, headers=headers)
    response.encoding = 'utf-8'
    
    if response.status_code != 200:
        print(f"Failed to fetch page: {response.status_code}")
        return []

    soup = BeautifulSoup(response.text, 'html.parser')
    products = []

    items = soup.select('.product_item')
    for item in items:
        name_el = item.select_one('.product_name')
        price_el = item.select_one('.price')
        link_el = item.select_one('a')
        stock_el = item.select_one('.stock_status')

        if name_el and price_el and link_el:
            name = name_el.get_text(strip=True)
            price_text = price_el.get_text(strip=True).replace(',', '').replace('￥', '').replace('円', '')
            try:
                price = int(''.join(filter(str.isdigit, price_text)))
            except ValueError:
                continue

            product_url = link_el.get('href', '')
            if not product_url.startswith('http'):
                product_url = BASE_URL + product_url.lstrip('/')

            in_stock = True
            if stock_el and "在庫なし" in stock_el.get_text():
                in_stock = False

            products.append({
                "name": name,
                "price": price,
                "category": "全般",
                "url": product_url,
                "in_stock": in_stock
            })
            
    return products

def update_supabase(products):
    for item in products:
        supabase.table('products').upsert(
            item, on_conflict='url'
        ).execute()
    print(f"Successfully updated {len(products)} products in Supabase.")

if __name__ == "__main__":
    items = fetch_sasabe_products()
    if items:
        update_supabase(items)
    else:
        print("No products found.")
