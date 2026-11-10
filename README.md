# sasabe-gacha

笹部洋画材料店（https://www.sasabegazai.co.jp/）の全商品データ・販売価格を日次でスクレイピングし、Supabase へ自動同期するリポジトリです。

## 概要
- **対象**: 全244シリーズ（絵の具、筆、キャンバス、額縁等）の実商品（約1.8万件）
- **実行基盤**: GitHub Actions（日次 04:00 JST 自動実行 ＆ 手動実行対応）
- **保存先**: Supabase (`products` テーブル)

## Supabase テーブル準備（初回のみ）

Supabase の SQL Editor で以下を実行して、テーブルを作成（または既存テーブルに `url` の UNIQUE 制約を追加）してください。

```sql
-- 既存テーブルがある場合（url に一意制約を追加）
TRUNCATE TABLE products;
ALTER TABLE products ADD CONSTRAINT products_url_unique UNIQUE (url);

-- 新規作成する場合
CREATE TABLE IF NOT EXISTS public.products (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name TEXT NOT NULL,
    price INTEGER,
    category TEXT,
    url TEXT NOT NULL UNIQUE,
    in_stock BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

## GitHub Actions Secrets

GitHub リポジトリの `Settings > Secrets and variables > Actions` に以下を登録してください。
- `SUPABASE_URL`
- `SUPABASE_KEY`
