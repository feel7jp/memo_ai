# Memo AI

**Notion をメモリとして使用するステートレス AI 秘書**です。
ユーザーの入力（テキスト、画像）を AI で解析し、構造化された Notion エントリに変換します。

> **必読**: 新しいタスクを開始する前に、必ずこのファイルを読んでください。
> 英語で思考し、ユーザーの入力言語(日本語など)で返答する。Implementation Plan、コードコメントはユーザーの言語(日本語など)で記述する。
- リダイレクトの使用禁止 (例: `pytest.py -v 2>&1 | Select-Object` など)
---

## Do (必ず行う)

- `.env` で設定管理。APIキーのハードコード禁止
- `DEBUG_MODE` を尊重。`False` の場合はデバッグ機能を隠す
- コード変更後は**手動リグレッションテスト**を実施（主要機能: Chat、Save、Content、Settings）
- **作業完了時のチェックリスト**を必ず実行:
  - Python: `pytest -v --tb=short` 全パス確認
  - JavaScript: `jsconfig.json` の型チェック有効時、IDE問題パネルでエラー0件確認
  - 意図した変更がすべて適用されているか確認
  - やり残しがないか、不要なものが残ってないか確認
  - 似た問題が他のファイルにないか確認（横断確認の原則）
- **横断確認の原則**: 1ファイルの問題を修正したら、同種の全ファイルを確認する
- ベストプラクティスを調査してから実装する

## Ask (事前確認が必要)

- `requirements.txt` への新パッケージ追加
- Notion データベーススキーマや API 呼び出しの変更
- コアモジュール (`main.js`, `chat.js`, `index.py`) の大規模リファクタリング
- API エンドポイントのシグネチャ変更

## Don't (禁止事項)

- 秘密情報のコミット (`.env`, API キー)
- SQLite, Postgres 等のローカル DB 追加提案 (Notion のみ使用)
- Webpack, Vite 等のビルドツール導入
- React, Vue, Next.js への移行提案
- リダイレクトの使用禁止 (例: `pytest.py -v 2>&1 | Select-Object` など)　使用許可を自動化できないため。

---

## Commands (ファイルスコープ優先)

```bash
# Python: 単一ファイルのテスト
pytest tests/test_specific.py -v --tb=short

# Python: 単一ファイルのlint
ruff check api/specific_file.py

# 全テスト（コミット前のみ）
pytest -v --tb=short

# 開発サーバー起動
python -m uvicorn api.index:app --reload --host 0.0.0.0
```

---

## Project Structure (全ファイル一覧)

### ルート

| ファイル | 責務 |
| :--- | :--- |
| `AGENTS.md` | このファイル（全体ルール・構造マップ） |
| `README.md` | プロジェクト概要・セットアップ手順 |
| `.env` / `.env.example` | 環境変数（APIキー、モデル設定など） |
| `.gitignore` | Git除外設定 |
| `requirements.txt` | Python依存パッケージ |
| `pyproject.toml` | Python プロジェクト設定（ruff, pytest等） |
| `pytest.ini` | pytest設定（テスト検出・オプション） |
| `package.json` | npm設定（TypeScriptの型チェック用） |
| `tsconfig.json` | TypeScript設定（JSDocベースの型チェック） |
| `vercel.json` | Vercelデプロイ設定（ルーティング、関数設定） |

---

### `api/` — バックエンド (Python / FastAPI)

| ファイル | 責務 |
| :--- | :--- |
| `AGENTS.md` | Backend固有ルール |
| `index.py` | **FastAPIアプリ本体** — ライフスパン管理、CORS、例外ハンドラ、静的ファイル配信、デバッグエンドポイント |
| `endpoints.py` | **全APIルート定義** — `/api/health`, `/api/config`, `/api/models`, `/api/targets`, `/api/schema`, `/api/content`, `/api/analyze`, `/api/chat`, `/api/save`, `/api/update`, `/api/create-page`。エラーレスポンスは `_build_error_detail()` で統一 |
| `ai.py` | **AIプロンプト構築** — スキーマ→プロンプト変換、JSON応答検証・修正、`analyze_text_with_ai()`, `chat_analyze_text_with_ai()` |
| `llm_client.py` | **LLM API通信** — LiteLLM経由の`generate_json()`, マルチモーダル対応, 画像生成(`generate_image_response()`), リトライ・コスト計算・通信ログ |
| `models.py` | **モデル管理** — 動的レジストリ構築、推奨モデルリスト、モデル自動選択(`select_model_for_input()`)、可用性チェック |
| `model_discovery.py` | **動的モデル発見** — Gemini/OpenAI APIから利用可能モデルを取得、1時間TTLキャッシュ |
| `notion.py` | **Notion API通信** — `safe_api_call()`（リトライ・指数バックオフ）、ページ/DB CRUD、スキーマ取得、ブロック追加 |
| `config.py` | **設定集約** — 全環境変数の読み込み・検証、APIキー管理、デフォルトモデル、LiteLLM設定、定数 |
| `schemas.py` | **Pydanticモデル** — `AnalyzeRequest`, `SaveRequest`, `ChatRequest` のリクエストスキーマ定義 |
| `services.py` | **ビジネスロジックヘルパー** — `extract_plain_text()`（plain_text抽出の共通化）、Base64画像除去、Notionプロパティサニタイズ・分割、タイトル自動生成、コンテンツブロック変換 |
| `rate_limiter.py` | **レート制限** — グローバル1000 req/h、エンドポイント別制限、自動クリーンアップ |
| `logger.py` | **ロギング基盤** — `setup_logger()` で全モジュール統一ログ、DEBUG_MODEでレベル自動切替 |
| `__init__.py` | パッケージ初期化 |

---

### `public/` — フロントエンド (Vanilla JS / CSS)

| ファイル | 責務 |
| :--- | :--- |
| `AGENTS.md` | HTML/CSS固有ルール |
| `index.html` | **エントリHTML** — 全UIの構造定義（チャット、モーダル群、ターゲット選択、設定パネル等） |
| `style.css` | **グローバルスタイル** — CSS変数、レスポンシブ、モーダル、チャットバブル、アニメーション |
| `favicon.svg` | ファビコン |

#### `public/js/` — JavaScriptモジュール

| ファイル | 責務 |
| :--- | :--- |
| `AGENTS.md` | JavaScript固有ルール |
| `main.js` | **エントリポイント** — グローバル状態(`App`)、ターゲット管理、保存処理、キャッシュ、初期化、ユーティリティ関数 |
| `chat.js` | **チャット機能** — メッセージ送受信(`handleChatAI()`)、履歴管理、レンダリング、スタンプ送信、Notion保存連携 |
| `images.js` | **画像処理** — カメラ撮影、画像圧縮、プレビュー表示/削除、画像生成モード切替 |
| `model.js` | **モデル選択UI** — モデル一覧取得・表示、選択モーダル、コスト表示 |
| `debug.js` | **デバッグ機能** — デバッグモーダル、API通信記録・コピー、DEBUG_MODE制御 |
| `prompt.js` | **プロンプト編集** — システムプロンプトモーダル、保存/リセット/ターゲット別読込 |
| `types.d.ts` | **グローバル型定義** — JSDocベースの型チェック用TypeScript定義ファイル |

---

### `tests/` — テストスイート (pytest)

| ファイル | 責務 |
| :--- | :--- |
| `AGENTS.md` | テスト固有ルール |
| `__init__.py` | パッケージ初期化 |
| `conftest.py` | **共通フィクスチャ** — モック設定、テスト用ヘルパー関数 |
| `test_api_contract.py` | **API契約テスト** — JS↔Backendのエンドポイント整合性を自動検証 |
| `test_html_js_consistency.py` | **HTML/JS整合性テスト** — HTML内のIDとJSの参照整合性を検証 |
| `test_current_api.py` | エンドポイントの単体テスト |
| `test_services.py` | `services.py` のヘルパー関数テスト |
| `test_extract_plain_text.py` | `extract_plain_text()` の単体テスト |
| `test_llm_client.py` | `llm_client.py` のLLM通信テスト |
| `test_ai_internal.py` | `ai.py` 内部ロジック（プロンプト構築、JSON検証）テスト |
| `test_enhanced.py` | 拡張テスト（エッジケース等） |
| `test_advanced_scenarios.py` | 高度なシナリオテスト |
| `test_critical_paths.py` | 重要パス（ハッピーパス）テスト |
| `test_gap_coverage.py` | カバレッジギャップの補完テスト |
| `test_response_shape.py` | APIレスポンス形状テスト |
| `test_regression_schemas.py` | スキーマリグレッションテスト |
| `test_rate_limiter.py` | レート制限ロジックテスト |
| `test_model_discovery.py` | モデル発見機能テスト |
| `test_json_mode_integration.py` | JSON Mode統合テスト |
| `test_image_gen_fix.py` | 画像生成修正の検証テスト |
| `debug_gemini_image_response.py` | デバッグ用: Gemini画像レスポンス検証スクリプト |
| `inspect_images.py` | デバッグ用: 画像データ検査スクリプト |
| `verify_e2e_image_gen.py` | デバッグ用: 画像生成E2E検証スクリプト |
| `manual/` | 手動テスト用スクリプト（Notion APIバージョン互換性チェック等） |

---

### `docs/` — ドキュメント

| ファイル | 責務 |
| :--- | :--- |
| `AGENTS.md` | **トラブルシューティング・デバッグパターン詳細ガイド** |

---

**参照**:
- トラブルシューティング・デバッグパターン → `docs/AGENTS.md`
- 環境変数テンプレート → `.env.example`

---

## When Stuck (行き詰まった時)

- 推測で大きな変更をしない。まず計画を提示して確認を求める
- 2回パッチを当てても直らない場合はフロー全体を図示する
- ベストプラクティスを調査してから対処する
- 対症療法は最大2回まで

---

## Key Patterns (重要パターン)

### 設計方針
| 原則 | 説明 |
| :--- | :--- |
| **ステートレス** | 内部DBなし。永続化は Notion API 経由のみ |
| **ローカル優先** | `uvicorn` + `.env` でのローカル開発に最適化 |
| **クロスプラットフォーム** | 起動コマンドはOS共通、設定は `.env` に集約 |

### リグレッション予防
- **API契約テスト**: `test_api_contract.py` がJS↔Backend整合性を自動検証（`pytest`実行時）
- API エンドポイント変更前に `public/` 内で該当文字列を検索し、全参照箇所を更新する
- CSS 変更時は**デスクトップ**と**モバイル**の両方で確認する
- AGENTS.mdが500行を超えたら、重要度の低い項目を要約または `docs/` に移動する

---

## 技術スタック

**Backend**: Python 3.9+, FastAPI, Uvicorn, LiteLLM  
**Frontend**: Vanilla JavaScript (ES6+), Vanilla CSS  
**禁止**: React, Vue, Webpack, Vite (軽量・シンプルを維持)

---

## 設計原則

### コード品質
- **デッドコード削除**: テスト専用関数は本番に不要。`grep_search`で使用箇所0件なら削除
- **DRY原則**: 3回以上の重複→ヘルパー関数に抽出（例：`extract_plain_text()`、`_build_error_detail()`、`getModelDisplayName()`）
- **ロギング統一**: バックエンドは `logger.info()`、フロントエンドは `App.debug.enabled` でガード
- **関数の責務**: 1関数50行超→分割検討。重複コードは即座にヘルパー化
