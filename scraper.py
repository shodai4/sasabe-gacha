import os
import re
import requests
from bs4 import BeautifulSoup
from supabase import create_client, Client

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("SUPABASE_URL と SUPABASE_KEY の環境変数が設定されていません。")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

BASE_URL = "https://www.sasabegazai.co.jp/"
# 404エラーを防ぐため、明確に index.html を指定
TARGET_URL = "https://www.sasabegazai.co.jp/index.html"

def fetch_sasabe_products():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        response = requests.get(TARGET_URL, headers=headers, timeout=15)
        response.encoding = response.apparent_encoding or 'utf-8'
    except Exception as e:
        print(f"Failed to connect: {e}")
        return []

    print(f"Response status: {response.status_code}")
    if response.status_code != 200:
        print(f"Failed to fetch page: {response.status_code}")
        return []

    soup = BeautifulSoup(response.text, 'html.parser')
    products = []
    seen_urls = set()

    # item.html?id= を含むリンクをすべて取得
    links = soup.find_all('a', href=re.compile(r'item\.html\?id='))

    for link in links:
        href = link.get('href', '')
        if not href.startswith('http'):
            product_url = BASE_URL + href.lstrip('/')
        else:
            product_url = href

        if product_url in seen_urls:
            continue
        seen_urls.add(product_url)

        # 親要素からテキストを取得して商品名や価格を探す
        parent = link.find_parent(['div', 'center', 'td', 'li'])
        parent_text = parent.get_text(separator=' ', strip=True) if parent else link.get_text(strip=True)

        # 商品名の決定
        name = ""
        img = link.find('img')
        if img and img.get('alt') and img.get('alt') != "商品画像":
            name = img.get('alt').strip()

        if not name and parent_text:
            clean_text = re.sub(r'(NEW|大特価|期間限定|\d+%OFF|定価.*)', '', parent_text).strip()
            clean_text = re.sub(r'\s+', ' ', clean_text)
            if len(clean_text) > 1 and "商品画像" not in clean_text:
                name = clean_text[:50]

        if not name:
            name = f"笹部画材の商品 (ID: {product_url.split('=')[-1]})"

        # 価格の抽出
        price = 1000
        price_match = re.search(r'(?:￥|\\)\s*([\d,]+)', parent_text)
        if price_match:
            price_str = price_match.group(1).replace(',', '')
            try:
                price = int(price_str)
            except ValueError:
                pass

        products.append({
            "name": name,
            "price": price,
            "category": "画材",
            "url": product_url,
            "in_stock": True
        })

    print(f"Found {len(products)} products.")
    return products

def update_supabase(products):
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
