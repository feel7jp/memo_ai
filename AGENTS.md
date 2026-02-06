# Memo AI - エージェントガイド

> **必読**: 新しいタスクを開始する前に、必ずこのファイルを読んでください。

---

## 1. プロジェクト概要

**Memo AI** は **Notion をメモリとして使用するステートレス AI 秘書**です。
ユーザーの入力（テキスト、画像）を AI で解析し、構造化された Notion エントリに変換します。
英語で思考し、ユーザーの言語で回答すること。
ユーザーが開発について学習できるように、状況、課題、対処法などをわかり易く説明すること。

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

## 4. UIアーキテクチャとデータフロー

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

## 5. 環境変数

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

## 7. テスト

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
| `tests/conftest.py` | 共通フィクスチャ、マーカー登録 |
| `tests/test_current_api.py` | 現API仕様のスモークテスト |
| `tests/test_enhanced.py` | 境界値・ロジックテスト |
| `tests/test_gap_coverage.py` | エラー処理・タイムアウト |
| `tests/test_advanced_scenarios.py` | セキュリティ・並行性 |
| `tests/test_critical_paths.py` | 統合フロー |
| `tests/test_regression_schemas.py` | スキーマ整合性 |

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

## 8. 🚨 頻発する問題と予防策 (重要)
うまく行かない場合、ベストプラクティスを調査する。
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

### 問題4: 作業完了後のヌケモレ

**症状**: 作業を完了したつもりでも、見落としや未完了の箇所が残っている
*   例: logger移行で一部ファイルを見落とす、テスト実行を忘れる、ドキュメント更新を忘れる

**必須チェックリスト（作業完了時）**:

#### 1. コード品質確認
```bash
# 意図した変更がすべて適用されているか
# やり残しがないか、不要なものが残ってないか。
# 型定義の更新が必要な箇所はないか
# lintエラーはないか
# 似た問題が他にないか確認する
```

#### 2. テスト実行
```bash
# 全テストが通ることを確認
pytest -v --tb=short
```

#### 3. 実行確認
- サーバーが正常に起動するか
- 主要機能が動作するか（Chat、Save、Settingsなど）

#### 4. ドキュメント更新
- `README.md`: 変更があれば更新
- `AGENTS.md`: 新しい問題パターンや予防策を追加。AGENTS.mdが500行を超えたら、重要度の低い項目を要点のみ端的に要約して減らす。
- `task.md`: 完了項目をチェック
- 完了レポート（walkthrough）: 変更内容を記録

#### 5. Git確認
```bash
# 意図しないファイルが含まれていないか
git status

# .envなど秘密情報が含まれていないか
git diff
```

**この確認を怠ると**:
- デグレッション（既存機能の破壊）
- 不完全な実装の放置
- 次の作業者が混乱

**予防策**:
-   CSS 変更時は **デスクトップ** と **モバイル** の両方で確認
-   削除前にブラウザ開発者ツールで影響範囲を確認

### 問題5: Vercel ビルドエラー（pyproject.toml）

**症状**: Vercel デプロイ時に `No [project] table found` エラー

**原因**: ローカルは `pip` + `requirements.txt`、Vercel は `uv` + `pyproject.toml` を使用。`uv` は `[project]` テーブルを必須とする。

**予防策**:
-   `pyproject.toml` に `[project]` テーブルを常に含める
-   依存関係を `pyproject.toml` と `requirements.txt` の両方に同期

---

## 9. UI実装ガイドライン

### 9.1 モーダルダイアログ実装チェックリスト

新しいモーダルを追加する際は、必ず以下を確認してください:

#### ❌ 禁止事項

- `alert()`, `confirm()`, `prompt()`などのブラウザネイティブダイアログを使用しない
- 独自のCSSクラスを作らず、既存のモーダル用クラスを使用する

#### ✅ 標準HTMLパターン

```html
<div id="xxxModal" class="modal hidden">
    <div class="modal-content">
        <div class="modal-header">
            <h2>タイトル</h2>
            <button id="closeXxxModalBtn" class="close-btn">×</button>
        </div>
        <div class="modal-body">
            <div class="modal-info">
                <label for="xxxInput"><strong>ラベル:</strong></label>
                <input type="text" id="xxxInput" class="target-select" 
                       style="width: 100%; margin-top: 8px;">
            </div>
        </div>
        <div class="modal-footer">
            <button id="cancelXxxBtn" class="btn-secondary">キャンセル</button>
            <button id="saveXxxBtn" class="btn-primary">保存</button>
        </div>
    </div>
</div>
```

#### ✅ 標準JavaScriptパターン

```javascript
function openXxxModal() {
    const modal = document.getElementById('xxxModal');
    const input = document.getElementById('xxxInput');
    const saveBtn = document.getElementById('saveXxxBtn');
    const cancelBtn = document.getElementById('cancelXxxBtn');
    const closeBtn = document.getElementById('closeXxxModalBtn');
    
    if (!modal || !input || !saveBtn || !cancelBtn || !closeBtn) return;
    
    input.value = '';
    modal.classList.remove('hidden');
    input.focus();
    
    const handleSave = () => {
        const value = input.value.trim();
        if (value) {
            modal.classList.add('hidden');
            // 保存処理
        } else {
            showToast('入力してください');
        }
    };
    
    const handleCancel = () => {
        modal.classList.add('hidden');
    };
    
    const onKeydown = (e) => {
        if (e.key === 'Enter') { e.preventDefault(); handleSave(); }
        else if (e.key === 'Escape') { handleCancel(); }
    };
    
    // {once: true}で自動クリーンアップ
    saveBtn.addEventListener('click', handleSave, {once: true});
    cancelBtn.addEventListener('click', handleCancel, {once: true});
    closeBtn.addEventListener('click', handleCancel, {once: true});
    input.addEventListener('keydown', onKeydown);
    
    const removeKeyListener = () => { input.removeEventListener('keydown', onKeydown); };
    saveBtn.addEventListener('click', removeKeyListener, {once: true});
    cancelBtn.addEventListener('click', removeKeyListener, {once: true});
    closeBtn.addEventListener('click', removeKeyListener, {once: true});
}
```

**参考実装**: `newPageModal` (main.js: 777-836), `promptModal` (prompt.js)

### 9.2 CSS クラス使用ガイドライン

#### モーダル専用クラス

| クラス名 | 用途 |
|:---|:---|
| `.modal` | モーダル全体のコンテナ |
| `.modal-content` | モーダルの中身 |
| `.modal-header` | ヘッダー部分 |
| `.modal-body` | ボディ部分 |
| `.modal-footer` | フッター部分 |
| `.modal-info` | 情報表示エリア（グレー背景） |
| `.close-btn` | ×閉じるボタン |
| `.btn-primary` | メインアクションボタン |
| `.btn-secondary` | キャンセルボタン |
| `.target-select` | 入力フィールド |

#### ❌ モーダルで使用禁止

`.prop-field`, `.prop-label`, `.prop-input` → これらは**プロパティフォーム専用**

### 9.3 イベントリスナー管理ベストプラクティス

#### パターン1: `{once: true}` オプション（推奨）

```javascript
button.addEventListener('click', handler, {once: true});
// ✅ 1回実行後に自動削除される
```

#### パターン2: `cloneNode()` による置換

```javascript
const newElement = element.cloneNode(true);
element.parentNode.replaceChild(newElement, element);
newElement.addEventListener('click', handler);
// ✅ 古いリスナーが確実に削除される
```

---

## 10. デバッグパターン

| 問題 | 調査場所 |
| :--- | :--- |
| API で 404 | `api/index.py` – ルート定義を確認 |
| Notion 保存失敗 | `api/notion.py` – ペイロードと API レスポンスを確認 |
| AI モデル未検出 | `api/config.py`, `.env` – API キーとモデル名を確認 |
| UI 要素が動かない | `public/js/main.js` または該当モジュール – イベントリスナーを確認 |

---

## 10. セキュリティ注意事項

> ⚠️ **これはデモ/教育目的のアプリケーションです。**

- デフォルトで**認証なし**。URL を知っていれば誰でもアクセス可能
- **レート制限**はオプション (`RATE_LIMIT_ENABLED=True` で有効化)
- **CORS** は緩い設定。本番では `ALLOWED_ORIGINS` で制限必須
- 本番環境向けの対策は `README.md` のセキュリティセクションを参照

---

## 11. 参考資料

- **README.md**: セットアップガイド、トラブルシューティング、カスタマイズ案
- **Knowledge Items (KIs)**: `.gemini/antigravity/knowledge/` 内の `memo_ai_project_guide` に詳細なアーキテクチャドキュメントあり

---

## 12. 開発環境の注意事項

> **📝 開発者への指示**: よくある問題とその対処法を発見した場合は、このセクションに追記してください。

### UTF-8/絵文字対応

Windows環境（cp932エンコーディング）では、Pythonの`print`文で絵文字を出力するとエラーになる場合がある。

**解決策**: `PYTHONUTF8=1` 環境変数を設定

```python
# conftest.py など、テスト/スクリプトの先頭で設定
import os
os.environ["PYTHONUTF8"] = "1"
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
