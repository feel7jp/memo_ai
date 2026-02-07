# Memo AI - エージェントガイド

> **必読**: 新しいタスクを開始する前に、必ずこのファイルを読んでください。

---

## プロジェクト概要

**Memo AI** は **Notion をメモリとして使用するステートレス AI 秘書**です。
ユーザーの入力（テキスト、画像）を AI で解析し、構造化された Notion エントリに変換します。
英語で思考し、ユーザーの言語で回答すること。
ユーザーが開発について学習できるように、状況、課題、対処法などをわかり易く説明すること。

### 必須チェックリスト（作業完了時）

#### コード品質確認
```bash
# Python: テスト + lint
pytest -v --tb=short

# JavaScript: プロジェクト設定に従った型チェック
# jsconfig.json の checkJs:true が有効 → IDEの問題パネルでエラー0件を確認
# node --check は構文エラーのみ。型エラーは検出しない
```
- 意図した変更がすべて適用されているか
- やり残しがないか、不要なものが残ってないか
- 似た問題が他のファイルにないか確認する（下記「横断確認の原則」参照）

#### テスト実行
```bash
# 全テストが通ることを確認
pytest -v --tb=short
```

#### 実行確認
- サーバーが正常に起動するか
- 主要機能が動作するか（Chat、Save、Settingsなど）

#### ドキュメント更新
- `README.md`: 変更があれば更新
- `AGENTS.md`: 繰り返す問題パターンや予防策を追加。
個別具体的ではなく、汎用的な問題を防止する対策として記述すること。
AGENTS.mdが500行を超えたら、重要度の低い項目を要点のみ端的に要約して減らす。

#### Git確認
```bash
# 意図しないファイルが含まれていないか
git status

```

**この確認を怠ると**:
- デグレッション（既存機能の破壊）
- 不完全な実装の放置
- 次の作業者が混乱

### 設計原則

| 原則 | 説明 |
| :--- | :--- |
| **ステートレス** | 内部DBなし。永続化は Notion API 経由のみ |
| **ローカル優先** | `uvicorn` + `.env` でのローカル開発に最適化 |
| **クロスプラットフォーム** | 起動コマンドはOS共通、設定は `.env` に集約 |
| **高速起動** | Notion データ優先読み込み、モデル検出は非同期 |

### 設計方針（安全性・信頼性）

| 方針 | 説明 |
| :--- | :--- |
| **問題に気付ける** | エラーを隠蔽せず、ログやUIで異常を検知・追跡可能にする |
| **事前に防げる** | テスト、型チェック、バリデーションにより、実行前のバグ発見に努める |
| **フェールセーフ** | 障害発生時もシステム全体を停止させず、安全な状態で動作を継続（縮退運転）させる |
| **フールプルーフ** | ユーザーの誤操作や想定外の入力があっても、システムが破損しないように保護する |

---

## 技術スタック

### バックエンド (`api/`)
| 項目 | 技術 |
| :--- | :--- |
| 言語 | Python 3.9+ |
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

## ディレクトリ構成

```
memo_ai/
├── api/                    # バックエンド (FastAPI)
│   ├── __init__.py         # パッケージ初期化
│   ├── index.py            # メインアプリケーション、CORS、lifespan
│   ├── endpoints.py        # API ルート定義（System, Notion, AI, Update系）
│   ├── ai.py               # プロンプト設計、AI モデル連携
│   ├── notion.py           # Notion API 統合
│   ├── config.py           # .env からの設定読み込み
│   ├── models.py           # Pydantic リクエスト/レスポンスモデル
│   ├── schemas.py          # データスキーマ定義
│   ├── services.py         # ビジネスロジック層
│   ├── model_discovery.py  # AI モデル動的検出
│   ├── llm_client.py       # LiteLLM ラッパー
│   ├── rate_limiter.py     # レート制限
│   └── logger.py           # 構造化ロギング設定
│
├── public/                 # フロントエンド (Vanilla JS)
│   ├── index.html          # メイン HTML
│   ├── style.css           # 全スタイル
│   ├── favicon.svg         # ファビコン
│   └── js/
│       ├── main.js         # エントリポイント、初期化、Notion ターゲット選択
│       ├── chat.js         # チャット UI: 吹き出し描画、履歴管理
│       ├── images.js       # 画像キャプチャ・処理
│       ├── prompt.js       # システムプロンプト管理
│       ├── model.js        # AI モデル選択 UI
│       ├── debug.js        # デバッグモーダル (DEBUG_MODE 時のみ)
│       └── types.d.ts      # TypeScript型定義（jsconfig.json経由）
│
├── tests/                  # テストスイート (pytest)
│   ├── conftest.py         # 共通フィクスチャ、マーカー登録、UTF-8出力設定
│   ├── test_*.py           # 各種テストファイル
│   └── __init__.py         # パッケージ初期化
│
├── .env                    # ローカル秘密情報 (コミット禁止)
├── .env.example            # .env のテンプレート
├── requirements.txt        # Python 依存関係
├── pyproject.toml          # プロジェクト設定、pytest設定（唯一の設定源）
└── vercel.json             # Vercel デプロイ設定
```

---

## UIアーキテクチャとデータフロー

### Notionプロパティの扱い

Notionデータベースにはプロパティがあり、それぞれTypeが決まっています（`title`, `rich_text`, `select`, `date`, `checkbox`など）。フロントエンドとバックエンドでのプロパティの扱いを理解することが重要です。

#### フロー概要

```
1. ターゲット選択時
   → /api/schema/{id} でスキーマ取得
   → App.target.schema に保存
   → renderDynamicForm() でフォーム生成

2. データ保存時
   → フォームから properties を収集
   → /api/save に送信
   → Notion API でページ作成
```

#### 重要な仕様

| プロパティ | 扱い | 理由 |
| :--- | :--- | :--- |
| **title** | フォームに**表示しない** | メイン入力欄（`memoInput`）の値を使用 |
| **created_time** | フォームに表示しない | Notion が自動管理 |
| **last_edited_time** | フォームに表示しない | Notion が自動管理 |
| その他 | フォームに表示する | ユーザーが手動で入力 |

#### titleプロパティの特殊処理

**重要**: `title`プロパティはフォームに表示されない（`main.js`の`renderDynamicForm`で`continue`）ため、**保存時にスキーマから検索して設定する必要があります**。

```javascript
// ❌ 間違い: フォームのinputsループだけで処理
inputs.forEach(input => {
    if (input.dataset.type === 'title') { // このinputは存在しない！
        properties[key] = { title: [...] };
    }
});

// ✅ 正しい: スキーマから検索して設定
if (window.App.target.schema) {
    for (const [key, prop] of Object.entries(window.App.target.schema)) {
        if (prop.type === 'title') {
            properties[key] = { title: [{ text: { content: content } }] };
            break;
        }
    }
}
```

この処理は以下の場所で実装されています：
- `chat.js` - `handleAddFromBubble()`: チャットバブルからの保存時
- `main.js` - `saveToDatabase()`: 直接保存時（今後実装予定）

#### データ構造の対応表

```javascript
// スキーマ（/api/schema レスポンス）
{
    "タスク名": { type: "title", title: {} },
    "ステータス": { type: "select", select: { options: [...] } },
    "期日": { type: "date", date: {} }
}

// プロパティペイロード（/api/save リクエスト）
{
    "タスク名": { title: [{ text: { content: "..." } }] },
    "ステータス": { select: { name: "進行中" } },
    "期日": { date: { start: "2026-02-06" } }
}
```

---

## 環境変数

`.env` の主要変数 (詳細は `.env.example` 参照):

| 変数名 | 必須 | 説明 |
| :--- | :--- | :--- |
| `NOTION_API_KEY` | ✅ | Notion Integration トークン |
| `NOTION_ROOT_PAGE_ID` | ✅ | データ保存先のルートページ ID |
| `GEMINI_API_KEY` | ✅ | Google Gemini API キー (デフォルト) |
| `OPENAI_API_KEY` | ❌ | OpenAI API キー (オプション) |
| `ANTHROPIC_API_KEY` | ❌ | Anthropic API キー (オプション) |
| `DEBUG_MODE` | ❌ | `True` でデバッグ機能有効化 |
| `DEFAULT_TEXT_MODEL` | ❌ | テキスト専用リクエストのデフォルトモデル |
| `DEFAULT_MULTIMODAL_MODEL` | ❌ | 画像+テキストのデフォルトモデル |
| `RATE_LIMIT_ENABLED` | ❌ | `True` でレート制限有効化 |
| `RATE_LIMIT_GLOBAL_PER_HOUR` | ❌ | 1時間あたりの総リクエスト数制限 |

---

## エージェント行動規範

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

## 起動コマンド

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

## テスト

### テスト実行
```bash
# 全テスト実行
pytest

# 詳細出力
pytest -v

# 失敗テストのみ再実行
pytest --lf

# 特定マーカーのテストのみ
pytest -m smoke      # 最重要テスト（CI用）
pytest -m regression # 全機能カバレッジ
pytest -m security   # セキュリティ関連
pytest -m integration # 統合テスト
```

### テストファイル構成
| ファイル | 目的 |
| :--- | :--- |
| `tests/conftest.py` | 共通フィクスチャ、マーカー登録、UTF-8出力設定 |
| `tests/test_current_api.py` | 現API仕様のスモークテスト |
| `tests/test_enhanced.py` | 境界値・ロジックテスト |
| `tests/test_gap_coverage.py` | エラー処理・タイムアウト |
| `tests/test_advanced_scenarios.py` | セキュリティ・並行性 |
| `tests/test_critical_paths.py` | 統合フロー |
| `tests/test_regression_schemas.py` | スキーマ整合性 |
| `tests/test_rate_limiter.py` | レート制限機能 |
| `tests/test_llm_client.py` | LLM API連携・リトライ |
| `tests/test_ai_internal.py` | プロンプト構築・JSON修復 |
| `tests/test_model_discovery.py` | モデル検出・キャッシュ |
| `tests/test_html_js_consistency.py` | HTML/JSセレクター整合性の静的解析 |

### エンドポイント移行時のテスト修正
`api/index.py` から `api/endpoints.py` へ関数を移行した場合、テスト内のモックパス修正が必要:

```python
# 移行前
with patch("api.index.fetch_children_list", ...):

# 移行後
with patch("api.endpoints.fetch_children_list", ...):
```

### ベストプラクティス (pytest + PowerShell)
- `pytest --lf` - 失敗テストのみ再実行
- `pytest -rf` - 失敗サマリー表示
- `pytest --tb=short` - 短いトレースバック
- PowerShell パイプより **直接 pytest オプション** を推奨

### エラー詳細出力フック (conftest.py)
テスト失敗時に詳細なデバッグ情報を自動出力する機能を `tests/conftest.py` に実装済み:

```
============================================================
[DEBUG] Test FAILED: test_analyze_endpoint
[DEBUG] Exception Type: NameError
[DEBUG] Exception Message: name 'AnalyzeRequest' is not defined
[DEBUG] ⚠️  Import/Module関連エラー検出!
[DEBUG] モックパスまたはimport文を確認してください
============================================================
```

**検出対象**:
- `ImportError`, `ModuleNotFoundError` → モジュールimport問題
- `AttributeError`, `NameError` → モックパスまたは関数名の問題
- ステータスコード不一致 → リクエストスキーマの確認を促す

---

## 🚨 頻発する問題と予防策 (重要)
うまく行かない場合、ベストプラクティスを調査する。
以下の問題が繰り返し発生しています。**必ず予防策を実施してください。**

### リファクタリング時の機能破壊

**症状**: ある機能の修正が無関係な機能を破壊する

**予防策**:
-  **手動リグレッションテスト**: コアファイル（`main.js`, `index.py` 等）を変更したら、主要機能（Chat、Save、Content、Settings）の動作を必ず確認

### API エンドポイントの不整合

**症状**: バックエンドのルート名変更後、フロントエンドが旧パスを参照し続けて 404 になる

**予防策**:
-   **変更前に検索**: ルート変更前に `public/` 内で該当文字列を検索し、全参照箇所を更新する

### UI/CSS のレグレッション

**症状**: 一箇所のスタイル修正が、別の場所のレイアウトを崩す

**予防策**:
-   CSS 変更時は **デスクトップ** と **モバイル** の両方で確認
-   削除前にブラウザ開発者ツールで影響範囲を確認

### 作業完了後のヌケモレ

**症状**: 変更対象の一部を見落とす、テスト実行やドキュメント更新を忘れる

**予防策**:
-   ファイル冒頭の **必須チェックリスト（作業完了時）** を必ず実行する

### 横断確認の原則

**症状**: 1ファイルの問題を修正したが、同じパターンの問題が他ファイルに残っている

**予防策**:
- **問題を1つ見つけたら、同種の全ファイルを確認する**。特定ファイルだけでなく、同じ技術（JS, Python等）の全ファイルに同じチェックを適用する
- チェック手段は**プロジェクト設定に従う**。独自の簡易チェックで済ませず、設定済みのツール（`jsconfig.json`の型チェック、`pytest`、`ruff`等）を使う
- 簡易チェック（`node --check`等）は構文エラーしか検出しない。型エラー・未使用変数・ベストプラクティス違反は検出できないことを認識する

### Vercel ビルドエラー（pyproject.toml）

**症状**: Vercel デプロイ時に `No [project] table found` エラー

**原因**: ローカルは `pip` + `requirements.txt`、Vercel は `uv` + `pyproject.toml` を使用。`uv` は `[project]` テーブルを必須とする。

**予防策**:
-   `pyproject.toml` に `[project]` テーブルを常に含める
-   依存関係を `pyproject.toml` と `requirements.txt` の両方に同期

### 「重複する」バグのデバッグ手順

**症状**: 同じ処理が多重実行される（ページ二重作成、リスト項目の重複表示 等）

**根本原因パターン**:
1. **トリガー側の多重発火**: イベントリスナーが蓄積し、1回の操作で複数回ハンドラが実行される
2. **処理チェーンの重複呼び出し**: 複数箇所から同じ関数が呼ばれ、処理が多重実行される
3. **暗黙のデフォルト値**: 引数の有無で挙動が変わる関数で、呼び出し側が意図しない動作を引き起こす

**予防策**:

#### デバッグ時の切り分け原則（最重要）
「重複する」バグに遭遇したら、パッチを当てる前にまず**どの段階で重複が発生しているか**を特定する:
```
① トリガー（イベント発火） → ② 処理（API呼び出し） → ③ 表示（DOM更新）
```
- **①が原因**: リスナーの蓄積・重複登録 → リスナーのクリーンアップを確認
- **②が原因**: 関数の多重呼び出し → grep で全呼び出し元を洗い出す
- **③が原因**: 描画ロジックのバグ → innerHTML のクリア忘れ等

#### イベントリスナーのクリーンアップ確認
モーダル等の繰り返し開閉される UI では、**全ての終了パス**（ボタンクリック、Enterキー、Escapeキー、×ボタン）でリスナーが削除されるか確認する

#### 対症療法は最大2回まで
2回パッチを当てても直らない場合は手を止め、フロー全体を図示してから根本原因を特定する

---

## UI実装ガイドライン

### モーダルダイアログ実装ルール

- `alert()`, `confirm()`, `prompt()` 等のネイティブダイアログは**使用禁止**
- 既存の `.modal` 系CSSクラス（`.modal`, `.modal-content`, `.modal-header`, `.modal-body`, `.modal-footer`, `.btn-primary`, `.btn-secondary` 等）を使う。独自クラスを作らない
- `.prop-field`, `.prop-label`, `.prop-input` はプロパティフォーム専用。モーダルには使用しない
- HTML構造: `.modal.hidden` > `.modal-content` > `.modal-header` + `.modal-body` + `.modal-footer`
- JS: 表示は `classList.remove('hidden')`、非表示は `classList.add('hidden')`
- **参考実装**: `newPageModal`（main.js）、`promptModal`（prompt.js）

### イベントリスナー管理

- **推奨**: `{once: true}` オプションで自動クリーンアップ
- **代替**: `cloneNode(true)` で要素を置換し、古いリスナーを確実に削除
- モーダル等の繰り返し開閉されるUIでは、全ての終了パス（ボタン、Enter、Escape、×）でリスナーが削除されるか確認する

---

## デバッグパターン

| 問題 | 調査場所 |
| :--- | :--- |
| API で 404 | `api/index.py` – ルート定義を確認 |
| Notion 保存失敗 | `api/notion.py` – ペイロードと API レスポンスを確認 |
| AI モデル未検出 | `api/config.py`, `.env` – API キーとモデル名を確認 |
| UI 要素が動かない | `public/js/main.js` または該当モジュール – イベントリスナーを確認 |

---

## セキュリティ注意事項

> ⚠️ **これはデモ/教育目的のアプリケーションです。**

- デフォルトで**認証なし**。URL を知っていれば誰でもアクセス可能
- **レート制限**はオプション (`RATE_LIMIT_ENABLED=True` で有効化)
- **CORS** は緩い設定。本番では `ALLOWED_ORIGINS` で制限必須
- 本番環境向けの対策は `README.md` のセキュリティセクションを参照

---

## 参考資料

- **README.md**: セットアップガイド、トラブルシューティング、カスタマイズ案
- **Knowledge Items (KIs)**: `.gemini/antigravity/knowledge/` 内の `memo_ai_project_guide` に詳細なアーキテクチャドキュメントあり

---

## 開発環境の注意事項

> **📝 開発者への指示**: よくある問題とその対処法を発見した場合は、このセクションに追記してください。

### UTF-8/絵文字対応

Windows環境（cp932エンコーディング）では、Pythonの`print`文で絵文字を出力するとエラーになる場合がある。

**解決策**: `conftest.py` の**モジュールレベル（import前）**で `sys.stdout` を再構成する。
`os.environ["PYTHONUTF8"] = "1"` だけでは pytest の内部エラーを防げない場合があるため。

```python
# tests/conftest.py の先頭（他のimportより前）
import sys, io

# Windows cp932対策: stdout/stderrをUTF-8に強制（Mac/Linuxではスキップ）
for s in ('stdout', 'stderr'):
    stream = getattr(sys, s)
    if hasattr(stream, 'encoding') and stream.encoding and stream.encoding.lower() != 'utf-8':
        setattr(sys, s, io.TextIOWrapper(
            stream.buffer, encoding='utf-8', errors='replace', line_buffering=True
        ))
```

### pytestデバッグのベストプラクティス

```powershell
# ❌ 悪い例（エラー情報が欠落する）
pytest -v 2>&1 | Select-String -Pattern "(passed|failed)"

# ✅ 良い例（全出力を確認）
pytest -v 2>&1 | Select-Object -Last 30
```

### モックパス規則（APIリファクタリング時）

エンドポイントを別モジュールに移行した場合、テストのモックパスも更新が必要：

```python
# 移行前: api/index.py にエンドポイントがある場合
@patch("api.index.some_function")

# 移行後: api/endpoints.py に移行した場合
@patch("api.endpoints.some_function")
```

### git checkout 使用時の注意

> ⚠️ **重要**: `git checkout` でファイルを戻す前に、必ず影響範囲を確認すること。

**問題となるケース**:
- ファイルAを編集中にエラー発生
- `git checkout A` で戻す
- **別ファイルBへの追加コードが失われる**（Aと連動して編集していた場合）

**対策**:
1. `git diff` で現在の変更を確認
2. 関連ファイルへの影響を把握してから戻す
3. 部分的な修正が可能なら、checkout より手動修正を優先
