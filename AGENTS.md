# Memo AI - エージェントガイド

> **必読**: 新しいタスクを開始する前に、必ずこのファイルを読んでください。

---

## 1. プロジェクト概要

**Memo AI** は **Notion をメモリとして使用するステートレス AI 秘書**です。
ユーザーの入力（テキスト、画像）を AI で解析し、構造化された Notion エントリに変換します。

### 設計原則

| 原則 | 説明 |
| :--- | :--- |
| **ステートレス** | 内部DBなし。永続化は Notion API 経由のみ |
| **ローカル優先** | `uvicorn` + `.env` でのローカル開発に最適化 |
| **クロスプラットフォーム** | 起動コマンドはOS共通、設定は `.env` に集約 |
| **高速起動** | Notion データ優先読み込み、モデル検出は非同期 |

---

## 2. 技術スタック

### バックエンド (`api/`)
| 項目 | 技術 |
| :--- | :--- |
| 言語 | Python 3.8+ |
| フレームワーク | FastAPI |
| サーバー | Uvicorn |
| AI クライアント | LiteLLM (Gemini, OpenAI, Anthropic 対応) |
| Notion | `notion-client` SDK |

### フロントエンド (`public/`)
| 項目 | 技術 |
| :--- | :--- |
| 言語 | Vanilla JavaScript (ES6+) |
| フレームワーク | **なし** (React, Vue 等は使用禁止) |
| スタイル | Vanilla CSS (モバイルファースト) |
| エントリポイント | `index.html` |

---

## 3. ディレクトリ構成

```
memo_ai/
├── api/                    # バックエンド (FastAPI)
│   ├── index.py            # メインルート: /api/chat, /api/save, /api/targets
│   ├── ai.py               # プロンプト設計、AI モデル連携
│   ├── notion.py           # Notion API 統合
│   ├── config.py           # .env からの設定読み込み
│   ├── models.py           # Pydantic リクエスト/レスポンスモデル
│   ├── model_discovery.py  # AI モデル動的検出
│   ├── llm_client.py       # LiteLLM ラッパー
│   └── rate_limiter.py     # レート制限 (1000 req/hr)
│
├── public/                 # フロントエンド (Vanilla JS)
│   ├── index.html          # メイン HTML
│   ├── style.css           # 全スタイル
│   └── js/
│       ├── main.js         # エントリポイント、初期化、Notion ターゲット選択
│       ├── chat.js         # チャット UI: 吹き出し描画、履歴管理
│       ├── images.js       # 画像キャプチャ・処理
│       ├── prompt.js       # システムプロンプト管理
│       ├── model.js        # AI モデル選択 UI
│       └── debug.js        # デバッグモーダル (DEBUG_MODE 時のみ)
│
├── .env                    # ローカル秘密情報 (コミット禁止)
├── .env.example            # .env のテンプレート
├── requirements.txt        # Python 依存関係
└── vercel.json             # Vercel デプロイ設定
```

---

## 4. 環境変数

`.env` の主要変数 (詳細は `.env.example` 参照):

| 変数名 | 必須 | 説明 |
| :--- | :--- | :--- |
| `NOTION_API_KEY` | ✅ | Notion Integration トークン |
| `NOTION_ROOT_PAGE_ID` | ✅ | データ保存先のルートページ ID |
| `GEMINI_API_KEY` | ✅ | Google Gemini API キー |
| `DEBUG_MODE` | ❌ | `True` でデバッグ機能有効化 |
| `DEFAULT_TEXT_MODEL` | ❌ | テキスト専用リクエストのデフォルトモデル |
| `DEFAULT_MULTIMODAL_MODEL` | ❌ | 画像+テキストのデフォルトモデル |
| `RATE_LIMIT_ENABLED` | ❌ | `True` でレート制限有効化 |

---

## 5. エージェント行動規範

### ✅ 必ず行うこと
- `.env` で設定管理。APIキーのハードコード禁止
- `DEBUG_MODE` を尊重。`False` の場合はデバッグ機能を隠す
- 依存関係変更時は `pip install -r requirements.txt` を実行
- コード変更後は**手動リグレッションテスト**を実施（後述）

### ❓ 事前確認が必要
- `requirements.txt` への新パッケージ追加
- Notion データベーススキーマや API 呼び出しの変更
- コアモジュール (`main.js`, `chat.js`) の大規模リファクタリング
- API エンドポイントのシグネチャ変更

### ❌ 禁止事項
- **秘密情報のコミット** (`.env`, API キー)
- SQLite, Postgres 等のローカル DB 追加提案 (Notion のみ使用)
- Webpack, Vite 等のビルドツール導入
- React, Vue, Next.js への移行提案

---

## 6. 起動コマンド

### 仮想環境の有効化
```bash
# Mac / Linux
source venv/bin/activate

# Windows (PowerShell)
venv\Scripts\Activate.ps1

# Windows (コマンドプロンプト)
venv\Scripts\activate
```

### 開発サーバー起動
```bash
# Mac / Linux / Windows 共通
python -m uvicorn api.index:app --reload --port 8000
```

### 依存関係インストール
```bash
pip install -r requirements.txt
```

### アクセス URL
- **ローカル**: http://localhost:8000
- **モバイル (同一ネットワーク)**: http://192.168.x.x:8000

---

## 7. 🚨 頻発する問題と予防策 (重要)

以下の問題が繰り返し発生しています。**必ず予防策を実施してください。**

### 問題1: リファクタリング時の機能破壊

**症状**: 一つの機能を修正すると、別の機能が壊れる
*   例: 「Add to Notion」修正 → 「Content Modal」が動かなくなる

**予防策**:
1.  **手動リグレッションテスト**: `main.js` または `index.py` を変更したら、以下を必ず確認:
    - ✅ **Chat**: メッセージ送信が動作する
    - ✅ **Save**: 「Notionに追加」が Notion に保存される
    - ✅ **Content**: 「Content」ボタンでモーダルが開く
    - ✅ **Settings**: モデル一覧が読み込まれる

### 問題2: API エンドポイントの不整合

**症状**: バックエンドでルート名を変更したが、フロントエンドが古いパスを呼び続ける
*   例: `/api/content` → `/api/get_content` に変更 → 404 エラー

**予防策**:
-   **変更前に検索**: `index.py` のルート変更前に、`public/` フォルダ内で該当文字列を検索

### 問題3: UI/CSS のレグレッション

**症状**: 一箇所のスタイル修正が、別の場所のレイアウトを崩す
*   例: ドロップダウンの余白修正 → リストの配置がずれる

**予防策**:
-   CSS 変更時は **デスクトップ** と **モバイル** の両方で確認
-   削除前にブラウザ開発者ツールで影響範囲を確認

---

## 8. デバッグパターン

| 問題 | 調査場所 |
| :--- | :--- |
| API で 404 | `api/index.py` – ルート定義を確認 |
| Notion 保存失敗 | `api/notion.py` – ペイロードと API レスポンスを確認 |
| AI モデル未検出 | `api/config.py`, `.env` – API キーとモデル名を確認 |
| UI 要素が動かない | `public/js/main.js` または該当モジュール – イベントリスナーを確認 |

---

## 9. セキュリティ注意事項

> ⚠️ **これはデモ/教育目的のアプリケーションです。**

- デフォルトで**認証なし**。URL を知っていれば誰でもアクセス可能
- **レート制限**はオプション (`RATE_LIMIT_ENABLED=True` で有効化)
- **CORS** は緩い設定。本番では `ALLOWED_ORIGINS` で制限必須
- 本番環境向けの対策は `README.md` のセキュリティセクションを参照

---

## 10. 参考資料

- **README.md**: セットアップガイド、トラブルシューティング、カスタマイズ案
- **Knowledge Items (KIs)**: `.gemini/antigravity/knowledge/` 内の `memo_ai_project_guide` に詳細なアーキテクチャドキュメントあり
