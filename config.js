// ==========================================
// 笹部画材ガチャ 外部設定ファイル (config.js)
// ==========================================
// Supabaseの管理画面（Project Settings > API）に表示されている
// 「Project URL」と「anon public key」をここに設定してください。
// ※管理者用の「service_role key」は絶対に設定しないでください。

window.APP_CONFIG = {
    // Supabase プロジェクトURL（例: "https://xxxxxxxxxxxxxxxx.supabase.co"）
    SUPABASE_URL: "https://xxzmrdfroqeflfgszgls.supabase.co",

    // Supabase 公開APIキー（anon public key: "eyJhbGci..."）
    SUPABASE_ANON_KEY: "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inh4em1yZGZyb3FlZmxmZ3N6Z2xzIiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTQyNzM2NTQsImV4cCI6MjEwOTg0OTY1NH0.To_PyTNca1yzXnxWMKGK9w4QF_1HZBCBB1xPKCrYZYo",

    // キャッシュ有効期間（ミリ秒: デフォルト6時間）
    CACHE_TTL_MS: 6 * 60 * 60 * 1000
};
