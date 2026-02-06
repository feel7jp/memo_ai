# Memo AI

Notionを記憶媒体として使用する、シンプルでカスタマイズ可能なAIアシスタントです。
ローカル環境で動作し、あなたの入力をNotionに構造化して保存します。
2026/02/06 大規模リファクタリングしました。モジュール分割など。

## 🚀 クイックスタート

Python 3.8以上が必要です。

### 1. セットアップ

ターミナルで以下を実行して、準備を整えます。

```bash
# 仮想環境の作成
python -m venv venv

# 仮想環境の有効化 (Windows)
venv\Scripts\activate
# 仮想環境の有効化 (Mac/Linux)
source venv/bin/activate

# 必要なパッケージのインストール
pip install -r requirements.txt
```

### 2. 設定 (.env)

プロジェクト直下に `.env` ファイルを作成し、APIキーを設定します。

1.  `.env.example` をコピーして `.env` にリネームします。
2.  以下の項目を入力します。

```env
# Google Gemini APIキー (必須)
# https://aistudio.google.com/app/apikey から取得
GEMINI_API_KEY=your_key_here

# Notion APIキー (Notion連携用)
# https://www.notion.so/my-integrations から取得
NOTION_API_KEY=your_key_here

# Notion ルートページID
# 共有設定　notionページの３点メニュー 接続 から上記で作成した integrations の名前を探す。
# ブラウザでNotionページを開き、URL末尾の32桁の英数字をコピー
# 例: https://notion.so/my-page-1234567890abcdef1234567890abcdef -> 1234567890abcdef1234567890abcdef
NOTION_ROOT_PAGE_ID=your_page_id_here
```

### 3. 起動

以下のコマンドでサーバーを立ち上げます。

```bash
# PC内でのみ利用する場合
python -m uvicorn api.index:app --reload --host 0.0.0.0
#  --host 0.0.0.0　スマホやタブレットからもアクセスしたい場合のオプション
```

ブラウザで `http://localhost:8000` にアクセスすれば完了です！

#### スマホ・タブレットからのアクセス方法

`--host 0.0.0.0` で起動した場合、同じWi-Fiネットワーク上のデバイスからアクセスできます。

1. サーバー起動時に表示されるIPアドレスを確認（例: `http://192.168.x.x:8000`）
2. スマホ・タブレットのブラウザでそのURLにアクセス

⚠️ **注意**: `--host 0.0.0.0` は同じネットワーク上の全デバイスからアクセス可能になります。公共のWi-Fiでは使用しないでください。

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

---

## 📚 AI開発 実践ガイド（初心者〜中級者向け）

このアプリのコードは、AI開発の重要なコンセプトを学ぶための教材としても機能します。

### 🔑 1. APIキーの管理
APIキーは大切な「鍵」です。他人に知られないように管理しましょう。

-   **コードに書かない**: キーは `.env` ファイルに書きます。これでGitへの誤送信を防げます。
-   **もし公開してしまったら**: キーを無効化し、再発行すれば大丈夫です。

### 🤖 2. エラーが出たらAIに聞こう
エラーでつまづいたら、エラーメッセージをそのままAI（ChatGPT, Gemini, Claudeなど）に貼り付けて質問するのが一番の近道です。

### 🛡️ 3. 実践的なセキュリティ対策
本番環境（インターネット公開）で運用する場合、以下の3つは「推奨」ではなく**「必須」**です。

| 対策 | 理由 |
|------|------|
| **認証を追加** | 現状は誰でもアクセス可能です。Basic認証やトークン認証を実装して、利用者を制限してください。 |
| **CORS設定** | `ALLOWED_ORIGINS` 環境変数を設定し、自分の公開ドメイン（例: `https://your-domain.com`）以外からの通信をブロックしてください。 |
| **コスト管理** | 従量課金API（OpenAI等）を利用する場合は、各サービスの管理画面で利用上限金額（Budget）を設定し、予期せぬ課金を防いでください。 |


### 🐛 4. デバッグのコツ
動かないときは、「どこで止まっているか」を探します。

1.  **ブラウザの検証ツール (F12)**:
    *   `Console` タブ: JavaScriptのエラー（赤文字）が出ていませんか？
    *   `Network` タブ: APIリクエスト (`/api/chat` など) が `200 OK` 以外（404や500）になっていませんか？
2.  **サーバーログ**:
    *   ターミナルを確認してください。Pythonのエラー詳細（Traceback）が表示されているはずです。

### 🔒 5. セキュリティガイドライン

#### APIキーの管理
API キーは `.gitignore` で保護されているため、Git にコミットされません。しかし、以下の点に注意してください：

-   スクリーンショットやログにAPIキーが含まれていないか確認
-   `.env` ファイルを誤って公開リポジトリにプッシュしない
-   もし漏洩した場合は、直ちにAPIキーを無効化して再発行

#### CORS設定（本番環境）

本番デプロイ時は **必ず** `ALLOWED_ORIGINS` 環境変数を設定してください：

```bash
# 例: Vercel環境変数設定
ALLOWED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com
```

⚠️ **未設定の場合のリスク**:
- 開発環境では全オリジン許可 (`*`) となり、本番環境でも予期しないアクセスを受ける可能性があります
- CSRF攻撃のリスクが高まります

#### DEBUG_MODE

`.env` ファイルの `DEBUG_MODE` は本番環境では **必ず** `False` に設定してください：

```env
# 本番環境
DEBUG_MODE=False

# 開発環境のみ
# DEBUG_MODE=True
```

`DEBUG_MODE=True` の場合、以下の機能が有効化されます：
- デバッグエンドポイント `/api/debug5075378` の公開
- 詳細なエラースタックトレースの出力
- モデル選択機能の有効化

---

