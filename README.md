# sasabe-gacha

笹部洋画材料店（https://www.sasabegazai.co.jp/）の全商品データ・販売価格を日次でスクレイピングし、Supabase へ自動同期＆「3,000円ガチャ」Webアプリを提供するリポジトリです。

## 概要
- **対象**: 全244シリーズ（絵の具、筆、キャンバス、額縁等）の実商品（約1.8万件）
- **実行基盤**: GitHub Actions（日次 04:00 JST 自動実行 ＆ 手動実行対応）
- **保存先**: Supabase (`products` テーブル)
- **フロントエンド**: `index.html`（GitHub Pagesで完全無料ホスティング可能、AdSense対応）

---

## 1. Supabase テーブル準備＆セキュリティ設定（RLS）

Supabase の SQL Editor で以下を実行してください。

```sql
-- テーブル作成（未作成の場合）
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

-- 【重要】一般公開に向けたセキュリティ設定（行レベルセキュリティ: RLS）
-- 外部の一般ユーザーには「読み取り（SELECT）」のみを許可し、データの改ざん・削除を防ぎます
ALTER TABLE public.products ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow public read-only" ON public.products FOR SELECT USING (true);
```

---

## 2. GitHub Actions Secrets（スクレイパー用）

GitHub リポジトリの `Settings > Secrets and variables > Actions` に以下を登録してください。
- `SUPABASE_URL`: SupabaseのProject URL（例: `https://xxxx.supabase.co`）
- `SUPABASE_KEY`: SupabaseのAPIキー（`service_role` または `anon`）

---

## 3. Webアプリ（ガチャ）の一般公開手順（GitHub Pages）

1. **Supabase接続キーの設定 (`index.html`)**:
   `index.html` 内の以下の箇所に、Supabaseの公開用キーを設定します。
   ```javascript
   const SUPABASE_URL = 'https://あなたのプロジェクト.supabase.co';
   const SUPABASE_ANON_KEY = 'あなたのanon_public_key';
   ```
   ※**注意**: 管理者用の `service_role key` は絶対に設定しないでください。必ず `anon public key` を使用してください。

2. **Google AdSenseの設定 (`index.html`)**:
   AdSenseの審査通過後、`index.html` 内の `ca-pub-XXXXXXXXXXXXXXXX` をご自身のパブリッシャーIDに書き換えます。

3. **GitHub Pagesで1クリック公開**:
   - リポジトリの `Settings` > `Pages` を開く
   - **Build and deployment** の `Source` を `Deploy from a branch` に設定
   - `Branch` を `main` / `/ (root)` に設定して「Save」をクリック
   - 数分後、`https://shodai4.github.io/sasabe-gacha/` で全世界に公開されます！
