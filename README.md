# Memo AI セットアップ＆起動ガイド

> **📢 重要なお知らせ**  
> 2026/01/09 0:00以前にgitを取得した方は、Vercelデプロイの問題が解決されているため、最新版を再取得してください。

> **⚠️ セキュリティに関する重要な注意**  
> このアプリケーションは**教育・学習目的のデモンストレーション**として設計されています。  
> **認証機能やレート制限がないため、本番環境での長期運用や公開URLの共有は推奨しません。**  
> 詳細は [セキュリティに関する注意事項](#セキュリティに関する注意事項) を必ずお読みください。

---

## 📋 目次
1. [前提条件の確認](#前提条件の確認)
2. [セットアップ手順](#セットアップ手順)
3. [起動方法](#起動方法)
4. [トラブルシューティング](#トラブルシューティング)
5. [セキュリティに関する注意事項](#セキュリティに関する注意事項)

---

## 前提条件の確認

### Python のインストール確認

ターミナルで以下を実行してバージョン確認：

```bash
python --version
または
python3 --version
```

> **💡 Python 3.8以上が必要です**  
> どちらか動作したコマンドを以降の手順で使用してください。  
> コマンドが見つからない場合は[Python公式サイト](https://www.python.org/downloads/)からインストール。

---

## セットアップ手順

### ステップ1: 仮想環境の作成

プロジェクトのフォルダに移動して、以下のコマンドを実行します：

> **� ここからは、先ほど確認した `python` または `python3` コマンドを使用してください**

**先ほど `python3` が使えた場合:**
```bash
python3 -m venv venv
```

**先ほど `python` が使えた場合:**
```bash
python -m venv venv
```

### ステップ2: 仮想環境の有効化

#### 📱 Mac / Linux の場合:
```bash
source venv/bin/activate
```

#### 🪟 Windows (コマンドプロンプト) の場合:
```bash
venv\Scripts\activate
```

#### 🪟 Windows (PowerShell) の場合:
```bash
venv\Scripts\Activate.ps1
```

> **✅ 成功の確認:**  
> ターミナルの行頭に `(venv)` と表示されれば成功です！

### ステップ3: 依存パッケージのインストール

仮想環境を有効化した状態で、以下のコマンドを実行してください：

```bash
pip install -r requirements.txt
```


### ステップ4: 環境変数の設定

1. プロジェクトフォルダに `.env` ファイルを作成します
2. .env.exampleを参考に、以下の環境変数を設定してください：

```env
# Gemini API キー（必須）
GEMINI_API_KEY=your_gemini_api_key_here

# Notion API トークン（Notion連携を使う場合）
NOTION_TOKEN=your_notion_token_here
NOTION_DATABASE_ID=your_database_id_here
```

> **🔑 APIキーの取得方法:**
> - **Gemini API**: [Google AI Studio](https://makersuite.google.com/app/apikey)
> - **Notion API**: [Notion Developers](https://www.notion.so/my-integrations)

Notionページ IDの取得方法
ページブロックを作成し、開く。
notionページのURLのうち、ハイフンより後ろの部分
www.notion.so/memoAI-2e137XXXXXXXXXXXXXff733 　　->　　 2e137XXXXXXXXXXXXXff733
.envの NOTION_ROOT_PAGE_ID=に設定する。

---

## 起動方法

仮想環境を有効化した状態で、以下のコマンドでサーバーを起動します：

```bash
python -m uvicorn api.index:app --reload --host 0.0.0.0
```

---

### ❓ よくあるエラーと対処法

#### `No module named uvicorn`
仮想環境を有効化して依存パッケージをインストール:
```bash
source venv/bin/activate  # Mac/Linux
# または
venv\Scripts\activate     # Windows

pip install -r requirements.txt
```

#### `Address already in use`
ポート8000が使用中です。以下のいずれかを実行:

**プロセスを終了:**
```bash
lsof -ti:8000 | xargs kill -9  # Mac/Linux
```

**別のポートを使用:**
```bash
# ポート番号を変更する場合は、PORT環境変数も設定してください
# (起動メッセージで正しいポート番号が表示されます)

# Mac/Linux (python3の場合)
PORT=8001 python3 -m uvicorn api.index:app --reload --host 0.0.0.0 --port 8001

# Mac/Linux (pythonの場合)
PORT=8001 python -m uvicorn api.index:app --reload --host 0.0.0.0 --port 8001

# Windows (コマンドプロンプト)
set PORT=8001 && python3 -m uvicorn api.index:app --reload --host 0.0.0.0 --port 8001

# Windows (PowerShell)
$env:PORT=8001; python3 -m uvicorn api.index:app --reload --host 0.0.0.0 --port 8001

# http://localhost:8001 でアクセス
```

---

## ✅ アクセス方法

サーバーが起動したら、ブラウザで以下のURLを開いてください:

```
http://localhost:8000
```

> **📱 スマートフォンからアクセスする場合:**  
> 起動時にターミナルに表示される `http://192.168.x.x:8000` のようなURLを使うと、同一ネットワーク内のモバイルデバイスからアクセスできます。

---

## トラブルシューティング

### ❌ `python3: command not found` と表示される (Mac/Linux)

**解決策:** `python` コマンドを試してください:
```bash
python --version
python -m venv venv
```

### ❌ `python: command not found` と表示される (Windows)

**解決策:** Pythonが正しくインストールされているか確認してください:
1. [Python公式サイト](https://www.python.org/downloads/)から最新版をダウンロード
2. インストール時に「Add Python to PATH」にチェックを入れる

### ❌ `Address already in use` エラー

**意味:** ポート8000が既に使われています

**解決策1:** 別のポートを使う
```bash
# Mac/Linux
python3 run_server.py --port 8001

# Windows
python run_server.py --port 8001
```

**解決策2:** 使用中のプロセスを終了する (Mac/Linux)
```bash
lsof -ti:8000 | xargs kill -9
```

**解決策2:** 使用中のプロセスを終了する (Windows)
```bash
netstat -ano | findstr :8000
taskkill /PID <プロセスID> /F
```

---

# 🛠️ 開発者・講義向け資料   (Hack Guide)

このアプリを改造したい人向けのガイドです。
NotionとAIをつなぐ「ステートレス」なアーキテクチャを採用しています。

## 1. アプリケーション概要 (Overview)
- **役割**: Notionを記憶媒体とするAI秘書
- **アーキテクチャ**:
  `Frontend (ブラウザ)` ↔ `Backend (FastAPI)` ↔ `External (Notion / Gemini)`
- **データ保存**: アプリ自体はデータベースを持ちません。すべてのデータはブラウザやNotionに保存されます。

## 2. ディレクトリ構造 (Directory Structure)

アプリケーションのファイル構成と各ファイルの役割を解説します。

```text
memo_ai/
├── public/          # フロントエンド (クライアントサイド)
│   ├── index.html   # UIレイアウト定義
│   ├── style.css    # スタイル定義 (デザイン・レスポンシブ対応)
│   └── script.js    # クライアントロジック (API通信、DOM操作)
│
├── api/             # バックエンド (サーバーサイド)
│   ├── index.py     # FastAPIエンドポイント定義 (ルーティング)
│   ├── ai.py        # AI連携処理 (Gemini API統合)
│   ├── notion.py    # Notion API統合 (データ永続化)
│   └── config.py    # 環境設定・モデル定義
│
└── .env             # 環境変数 (APIキー、シークレット)
```

## 3. データの流れ (Data Flow)

### 💬 チャットの流れ
1. **あなた**: メッセージを入力して送信
2. **script.js**: `/api/chat` にテキストと画像を送る
3. **index.py**: リクエストを受け取り、`ai.py` に依頼
4. **ai.py**: Notionの情報をコンテキストに含めてAIに解析させる
5. **画面**: AIの返答を表示

### 💾 保存の流れ
1. **あなた**: 吹き出しタップ →「Notionに追加」
2. **script.js**: `/api/save` に保存データを送る
3. **index.py**: 受け取ったデータを `notion.py` に渡す
4. **notion.py**: Notion APIを使って実際にページやDBに行を追加

## 4. 改造ガイド (Level別)

### Level 1 🐣 AIの性格を変える
**ターゲット**: `public/script.js`
AIへの「システムプロンプト（命令書）」を変更します。
`12行目周辺` にある `DEFAULT_SYSTEM_PROMPT` を書き換えてみましょう。
```javascript
const DEFAULT_SYSTEM_PROMPT = `あなたは大阪弁の陽気なアシスタントです...`;
```

### Level 2 🎨 デザインを変える
**ターゲット**: `public/style.css`
色やボタンの形を変えます。
例えば、自分のメッセージの背景色を変えるには `.chat-bubble.user` を探します。
```css
.chat-bubble.user {
    background-color: #0084ff; /* ここを好きな色に */
}
```

### Level 3 🔧 Notionへの保存項目を増やす
**ターゲット**: `api/index.py` (SaveRequest), `public/script.js` (saveToDatabase)
例えば「重要度」というセレクトボックスを追加したい場合：
1. `index.html` に `<select>` を追加
2. `script.js` でその値を取得して送信データに含める
3. `api/index.py` で受け取れるようにする

---

## ⚠️ セキュリティに関する注意事項

### 🎓 本アプリケーションの位置づけ

このアプリケーションは**教育・学習目的のデモンストレーション**として設計されています。  
コードのシンプルさと学習のしやすさを優先し、本番環境向けの複雑なセキュリティ機能は実装していません。

### 🚨 現在の主な制限事項

| 項目 | 現状 | リスク |
|------|------|--------|
| **認証機能** | ❌ なし | 誰でもAPIエンドポイントにアクセス可能 |
| **レート制限** | ❌ なし | 大量リクエストによるコスト急増の可能性 |
| **CORS設定** | ⚠️ 全オリジン許可 | 不正なウェブサイトからのアクセスが可能 |
| **入力検証** | △ 基本的なもののみ | 悪意のある大量データ送信のリスク |

### ✅ 安全な使用方法

以下の用途での使用を推奨します：

- ✅ **ローカル開発環境**での学習・実験
- ✅ **短期間のデモンストレーション**（数時間〜数日）
- ✅ **プライベートなテスト**（自分のみがアクセス）
- ✅ **講義や勉強会**での教材として

### ❌ 避けるべき使用方法

以下の用途での使用は**推奨しません**：

- ❌ 本番環境での長期運用
- ❌ 公開URLの不特定多数への共有
- ❌ 機密情報・個人情報の保存
- ❌ 24時間365日の稼働

### 💡 Vercel等への公開デプロイ時の注意

Vercelなどにデプロイして公開URLを取得できますが、以下のリスクを理解した上で使用してください：

1. **APIキーの保護**
   - 環境変数が正しく設定されているか確認
   - `.env`ファイルは絶対にGitにコミットしない

2. **アクセスログの確認**
   - Vercelのダッシュボードで異常なアクセスがないか定期確認
   - 不審なリクエストが多い場合は即座にデプロイを停止

3. **コスト監視**
   - Gemini API / Notion APIの使用量を定期的にチェック
   - 予期しない課金が発生していないか確認

4. **デプロイの停止方法**
   ```bash
   # Vercel CLIでプロジェクトを削除
   vercel remove memo-ai
   
   # または、Vercelダッシュボードから削除
   ```

### 🛡️ 本番環境で使用する場合の必須対策

もしこのアプリを本番環境で運用する場合は、最低限以下の対策を実装してください：

#### 1. 認証機能の追加

```python
# 例: シンプルなトークン認証
from fastapi import HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()
API_TOKEN = os.getenv("API_SECRET_TOKEN")

async def verify_token(credentials: HTTPAuthorizationCredentials = Security(security)):
    if credentials.credentials != API_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid token")

@app.post("/api/chat")
async def chat(request: ChatRequest, _: None = Depends(verify_token)):
    # ...
```

#### 2. CORS設定の厳格化

```python
# api/index.py を修正
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:8000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,  # 特定のドメインのみ
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)
```

`.env`に追加：
```env
ALLOWED_ORIGINS=https://yourdomain.vercel.app,https://www.yourdomain.com
```

#### 3. レート制限の実装

```bash
pip install slowapi
```

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@app.post("/api/chat")
@limiter.limit("10/minute")
async def chat(request: Request, chat_req: ChatRequest):
    # ...
```

#### 4. 環境変数の検証

起動時に必須環境変数をチェック：

```python
# api/config.py に追加
def validate_env():
    required = ["NOTION_API_KEY", "GEMINI_API_KEY", "NOTION_ROOT_PAGE_ID"]
    missing = [k for k in required if not os.getenv(k)]
    if missing:
        raise ValueError(f"Missing: {', '.join(missing)}")

validate_env()
```

### 📚 詳細情報

セキュリティ評価の詳細は以下のドキュメントを参照してください：

- **包括的なセキュリティ評価**: `security_assessment.md`（アーティファクトディレクトリ内）
- **推奨対策の詳細**: `security_recommendations.md`（アーティファクトディレクトリ内）

---

**最終更新**: 2026-01-10  
**目的**: 教育・学習用デモアプリケーション  
**推奨用途**: ローカル開発環境での短期間の実験・学習
