# Troubleshooting & Development Environment Guide

このファイルは、開発中に遭遇する可能性のある環境固有の問題とその対処法をまとめたリファレンスです。

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

## 開発環境の注意事項

### UTF-8/絵文字対応

Windows環境（cp932エンコーディング）では、Pythonの`print`文で絵文字を出力するとエラーになる場合があります。

**解決策**: `conftest.py` の**モジュールレベル（import前）**で `sys.stdout` を再構成します。
`os.environ["PYTHONUTF8"] = "1"` だけでは pytest の内部エラーを防げない場合があるためです。

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

## セキュリティ注意事項

> ⚠️ **これはデモ/教育目的のアプリケーションです。**

- デフォルトで**認証なし**。URL を知っていれば誰でもアクセス可能
- **レート制限**はオプション (`RATE_LIMIT_ENABLED=True` で有効化)
- **CORS** は緩い設定。本番では `ALLOWED_ORIGINS` で制限必須
- 本番環境向けの対策は `README.md` のセキュリティセクションを参照

---

## エンドポイント移行時のテスト修正

`api/index.py` から `api/endpoints.py` へ関数を移行した場合、テスト内のモックパス修正が必要:

```python
# 移行前
with patch("api.index.fetch_children_list", ...):

# 移行後
with patch("api.endpoints.fetch_children_list", ...):
```

---

## エラー詳細出力フック (conftest.py)

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

## LLM JSON Mode 互換性

### 問題: `"JSON mode is not enabled for this model"` エラー

**症状**: 画像生成モデル (`gemini-2.5-flash-image` 等) で JSON mode エラーが発生

**根本原因**: 画像生成モデルは JSON 構造化出力をサポートしていない

**解決策 (実装済み)**:

システムは **3層防御** で自動的にJSON mode対応を判定します:

#### Layer 1: Runtime Check (`llm_client.py`)
```python
# litellm公式APIで呼び出し時に自動チェック
model_supports_json = supports_response_schema(model=model)
if model_supports_json:
    extra_kwargs["response_format"] = {"type": "json_object"}
```

#### Layer 2: Name Heuristic (`model_discovery.py`)
```python
# モデル名から画像生成モデルを検出
is_image_generation = "image" in model_name.lower()
# メタデータに正確な情報を設定
"supports_json": not is_image_generation
```

#### Layer 3: Mode Override (`models.py`)
```python
# litellm の mode フィールドで二重チェック
if cost_info.get("mode") == "image_generation":
    gemini_model["supports_json"] = False
```

**検証コマンド**:
```python
import litellm
print(litellm.supports_response_schema("gemini/gemini-2.5-flash-image"))  # False
print(litellm.supports_response_schema("gemini/gemini-2.5-flash"))        # True
```

**参考**: [Implementation Plan](file:///C:/Users/kibit/.gemini/antigravity/brain/45678ccb-4375-487b-bf83-234a54dba3e2/implementation_plan.md) | [Walkthrough](file:///C:/Users/kibit/.gemini/antigravity/brain/45678ccb-4375-487b-bf83-234a54dba3e2/walkthrough.md)


---

## UI/CSS のレグレッション予防

**症状**: 一箇所のスタイル修正が、別の場所のレイアウトを崩す

**予防策**:
- CSS 変更時は **デスクトップ** と **モバイル** の両方で確認
- 削除前にブラウザ開発者ツールで影響範囲を確認

---

## ディレクトリ構成（完全版）

```
memo_ai/
├── api/                    # バックエンド (FastAPI)
│   ├── AGENTS.md           # Backend固有ルール
│   ├── __init__.py         # パッケージ初期化
│   ├── index.py            # メインアプリケーション、CORS、lifespan
│   ├── endpoints.py        # API ルート定義（System, Notion, AI, Update系）
│   ├── ai.py               # プロンプト設計、AI モデル連携
│   ├── notion.py           # Notion API 統合
│   ├── config.py           # .env からの設定読み込み
│   ├── models.py           # Pydantic リクエスト/レスポンスモデル
│   ├── schemas.py          # データスキーマ定義
│   ├── services.py         # ビジネスロジック層（extract_plain_text、サニタイズ、ブロック変換）
│   ├── model_discovery.py  # AI モデル動的検出
│   ├── llm_client.py       # LiteLLM ラッパー
│   ├── rate_limiter.py     # レート制限
│   └── logger.py           # 構造化ロギング設定
│
├── public/                 # フロントエンド (Vanilla JS)
│   ├── AGENTS.md           # Frontend固有ルール
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
├── docs/                   # ドキュメント（参照用）
│   └── AGENTS.md  # このファイル
│
├── .env                    # ローカル秘密情報 (コミット禁止)
├── .env.example            # .env のテンプレート
├── pytest.ini              # pytest設定（テスト検出・マーカー）
├── requirements.txt        # Python 依存関係
└── vercel.json             # Vercel デプロイ設定
```

---

## 参考資料

- **README.md**: セットアップガイド、トラブルシューティング、カスタマイズ案
- **Knowledge Items (KIs)**: `.gemini/antigravity/knowledge/` 内の `memo_ai_project_guide` に詳細なアーキテクチャドキュメントあり
