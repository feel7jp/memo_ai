# Memo AI

Notionを記憶媒体として使用する、シンプルでカスタマイズ可能なAIアシスタントです。
ローカル環境で動作し、あなたの入力をNotionに構造化して保存します。

> **🔄 2026/02/08 大規模リファクタリング実施** — モジュール分割、サービスレイヤー導入、テスト整備など

---

## ✨ 主な機能

| 機能 | 説明 |
|------|------|
| 💬 **AIチャット** | マルチモデル対応（Gemini / OpenAI / Anthropic）。LiteLLMによる統一インターフェース |
| 🎨 **画像生成** | Gemini の画像生成対応モデルで画像を生成（モデル選択画面の 🎨 アイコンが目印） |
| 📷 **画像入力** | 写真やスクリーンショットを送信してAIに分析・タスク化させるマルチモーダル対応 |
| 📝 **Notion連携** | ページへの追記・データベースへのアイテム作成に対応。AIがプロパティを自動推定 |
| 🔍 **デバッグ情報** | AIアシスタントにそのまま貼り付けられる構造化されたデバッグモーダル |
| 📱 **レスポンシブ** | スマホ・タブレットからもアクセス可能 |

---

## 🚀 セットアップ

### 前提条件

- Python 3.9以上

### 1. 環境変数の設定 (.env)

プロジェクト直下の `.env.example` をコピーして `.env` にリネームし、以下の項目を入力します。

```env
# Google Gemini APIキー (必須)
# https://aistudio.google.com/app/apikey から取得
GEMINI_API_KEY=your_key_here

# Notion APIキー (Notion連携用)
# https://www.notion.so/my-integrations から取得
NOTION_API_KEY=your_key_here

# Notion ルートページID
# ブラウザでNotionページを開き、URL末尾の32桁の英数字をコピー
# 例: https://notion.so/my-page-1234567890abcdef... -> 末尾の32桁
NOTION_ROOT_PAGE_ID=your_page_id_here
```

<details>
<summary>📌 その他の設定項目（任意）</summary>

| 変数名 | 説明 |
|--------|------|
| `NOTION_CONFIG_DB_ID` | システムプロンプト格納用の Notion Config DB |
| `OPENAI_API_KEY` | OpenAI モデルを使用する場合 |
| `ANTHROPIC_API_KEY` | Anthropic (Claude) モデルを使用する場合 |
| `DEFAULT_TEXT_MODEL` | デフォルトのテキストモデル指定 |
| `DEFAULT_MULTIMODAL_MODEL` | デフォルトのマルチモーダルモデル指定 |
| `DEBUG_MODE` | `True` でデバッグ機能を有効化（**本番では必ず `False`**） |
| `RATE_LIMIT_ENABLED` | レート制限の有効化（デフォルト: `True`） |
| `RATE_LIMIT_GLOBAL_PER_HOUR` | 1時間あたりのリクエスト上限（デフォルト: `1000`） |
| `ALLOWED_ORIGINS` | CORS許可オリジン（カンマ区切り） |

詳細は `.env.example` を参照してください。

</details>

### 2. インストール

```bash
# 仮想環境の作成
python -m venv venv

# 仮想環境の有効化 (Windows)
venv\Scripts\activate
# 仮想環境の有効化 (Mac/Linux)
source venv/bin/activate

# パッケージのインストール
pip install -r requirements.txt
```

### 3. 起動

```bash
python -m uvicorn api.index:app --reload --host 0.0.0.0
```

ブラウザで `http://localhost:8000` にアクセスすれば完了です！

> **💡 ヒント**: ポート8000が既に使用中の場合、`--port 8001` のようにポートを指定できます。

#### スマホ・タブレットからのアクセス

`--host 0.0.0.0` で起動した場合、同じWi-Fiネットワーク上のデバイスからアクセスできます。

1. サーバー起動時に表示されるIPアドレスを確認（例: `http://192.168.x.x:8000`）
2. スマホ・タブレットのブラウザでそのURLにアクセス

⚠️ **注意**: `--host 0.0.0.0` は同じネットワーク上の全デバイスからアクセス可能になります。公共のWi-Fiでは使用しないでください。

---

## ☁️ Vercel デプロイ

### 前提条件
- GitHub リポジトリと Vercel アカウントを連携済み
- `public/` 内の静的ファイルは Vercel CDN が自動配信（FastAPI側のマウント不要）

### 環境変数の設定

Vercel ダッシュボード → Settings → Environment Variables に以下を追加：

| 変数名 | 必須 | 備考 |
|--------|------|------|
| `GEMINI_API_KEY` | ✅ | Google AI Studio から取得 |
| `NOTION_API_KEY` | ✅ | Notion Integration トークン |
| `NOTION_ROOT_PAGE_ID` | ✅ | 32桁の英数字（ハイフンなし） |
| `ALLOWED_ORIGINS` | 推奨 | `https://your-domain.vercel.app`（CORS制限） |
| `DEBUG_MODE` | ❌ | **本番では必ず `False`**（デフォルト`False`） |

### ⚠️ サーバーレス環境の制約

| 制約 | 内容 | 対策 |
|------|------|------|
| **タイムアウト** | Hobby: 最大60秒 / Pro: 最大300秒 | AI API呼び出しが長い場合はPro推奨 |
| **バンドルサイズ** | 非圧縮250MB上限 | `excludeFiles` で `tests/`, `venv/` 等を除外 |
| **コールドスタート** | 初回アクセス時に数秒のレイテンシ | LiteLLM等の大きいパッケージは影響大 |
| **ステートレス** | リクエスト間で状態が保持されない | レート制限はインメモリのためリセットされる |

### よくあるデプロイエラー

| エラー | 原因 | 対処 |
|--------|------|------|
| 静的ファイルの404 | `public/` が CDN 配信されていない | Vercelのプロジェクト設定で Output Directory を確認 |
| API 504 Timeout | AI処理がプランの制限時間を超過 | `maxDuration` を引き上げるか Pro プラン |
| 依存パッケージ不足 | `requirements.txt` の依存関係が不足 | `requirements.txt` を確認 |

---

## 🛠️ カスタマイズ

コードを少し編集するだけで、自分だけのAIを作れます。
AIに改造アイデアを提案させることも可能。

### AIの性格を変える
`public/js/prompt.js` の `DEFAULT_SYSTEM_PROMPT` を編集します。
```javascript
// 例: 関西弁のAIにする
const DEFAULT_SYSTEM_PROMPT = `あなたは大阪出身の陽気なアシスタントです。`;
```

### デザインを変える
`public/style.css` で色や配置を調整できます。
```css
/* 例: 自分の吹き出しを青色にする */
.chat-bubble.user {
    background-color: #0084ff;
}
```



### 💡 改造アイデアの例

- **📷 家計簿ボット**: レシートの写真を送信して、金額・店名・日付をNotionの家計簿データベースに自動登録させる
- **🎤 音声入力メモ**: ブラウザ標準の音声認識API (`webkitSpeechRecognition`) を組み込み、声でメモを取れるようにする
- **📅 日報作成アシスタント**: 「今日完了したタスクをまとめて」と頼むと、Notionから完了タスクを抽出して日報形式で出力する
- **☀️ 天気予報連携**: 天気予報APIを叩くツールを追加し、「明日の天気は？」と聞くと答えてくれる機能を追加する

---

## 🏗️ プロジェクト構成

```
memo_ai/
├── public/                     # フロントエンド
│   ├── index.html              # UI レイアウト
│   ├── style.css               # レスポンシブデザイン
│   ├── favicon.svg             # ファビコン
│   └── js/                     # JavaScript モジュール
│       ├── main.js             # エントリーポイント & Notion ロジック
│       ├── chat.js             # チャット送受信
│       ├── images.js           # 画像入力・生成
│       ├── model.js            # モデル選択 UI
│       ├── prompt.js           # システムプロンプト管理
│       ├── debug.js            # デバッグ情報モーダル
│       └── types.d.ts          # TypeScript 型定義
│
├── api/                        # バックエンド (Python / FastAPI)
│   ├── index.py                # アプリ初期化・ミドルウェア設定
│   ├── endpoints.py            # 全APIルート定義
│   ├── ai.py                   # AI統合ロジック・プロンプト構築
│   ├── notion.py               # Notion API連携
│   ├── llm_client.py           # LiteLLM クライアントラッパー
│   ├── model_discovery.py      # 動的モデル発見・キャッシュ
│   ├── models.py               # AIモデル定義・ホワイトリスト
│   ├── schemas.py              # Pydantic リクエスト/レスポンス定義
│   ├── services.py             # ビジネスロジックヘルパー
│   ├── config.py               # 環境変数・定数の集中管理
│   ├── rate_limiter.py         # レート制限
│   └── logger.py               # 構造化ロギング
│
├── tests/                      # テストスイート (pytest)
├── vercel.json                 # Vercel デプロイ設定
├── requirements.txt            # Python 依存関係
└── .env.example                # 環境変数テンプレート
```

---

## 🧪 開発者向け

### テストの実行

```bash
# 全テスト実行
pytest

# 特定のテストファイル
pytest tests/test_services.py

# 詳細出力
pytest -v
```

### 型チェック (TypeScript)

フロントエンドJSの型定義は `public/js/types.d.ts` で管理しています。

```bash
npm run type-check
```

---

## 🔒 セキュリティ

本番環境（インターネット公開）で運用する場合の**必須**対策：

| 対策 | 方法 |
|------|------|
| **認証を追加** | 現状は誰でもアクセス可能です。Basic認証やトークン認証を実装して利用者を制限 |
| **CORS設定** | `ALLOWED_ORIGINS` に自分の公開ドメインを設定（未設定時は開発環境で全オリジン許可） |
| **コスト管理** | 従量課金APIの管理画面で利用上限金額（Budget）を設定 |
| **DEBUG_MODE** | **必ず `False`** に設定。`True` の場合デバッグエンドポイントが公開される |
| **APIキー管理** | `.env` ファイルをGitにコミットしない（`.gitignore` で保護済み）。漏洩時は即座に再発行 |

---

## 📚 AI開発 実践ガイド（初心者向け）

このアプリのコードは、AI開発の重要なコンセプトを学ぶための教材としても機能します。

### 🔑 APIキーの管理
APIキーは大切な「鍵」です。他人に知られないように管理しましょう。

-   **コードに書かない**: キーは `.env` ファイルに書きます。これでGitへの誤送信を防げます。
-   **もし公開してしまったら**: キーを無効化し、再発行すれば大丈夫です。

### 🤖 エラーが出たらAIに聞こう
エラーでつまづいたら、エラーメッセージをそのままAI（ChatGPT, Gemini, Claudeなど）に貼り付けて質問するのが一番の近道です。

### 🐛 デバッグのコツ
動かないときは、「どこで止まっているか」を探します。

1.  **ブラウザの検証ツール (F12)**:
    *   `Console` タブ: JavaScriptのエラー（赤文字）が出ていませんか？
    *   `Network` タブ: APIリクエスト (`/api/chat` など) が `200 OK` 以外（404や500）になっていませんか？
2.  **サーバーログ**:
    *   ターミナルを確認してください。Pythonのエラー詳細（Traceback）が表示されているはずです。

---
