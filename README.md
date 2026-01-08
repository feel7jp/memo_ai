# Memo AI Launch Instructions

## 前提条件
- Python 3.8+ がインストールされていること
- pip がインストールされていること

## セットアップ

1. 仮想環境の作成と有効化:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

2. 依存関係のインストール:
   ```bash
   pip install -r requirements.txt
   ```

3. 環境変数の設定:
   `.env` ファイルを作成し、必要な環境変数を設定してください（Notion APIキー、Gemini APIキーなど）。

## 起動方法

以下のコマンドを実行してサーバーを起動します:

```bash
python3 -m uvicorn api.index:app --reload --host 0.0.0.0
```

## アクセス

ブラウザで以下のURLにアクセスしてください:

- http://localhost:8000

起動時にターミナルに表示されるURLから、同一ネットワーク内のモバイルデバイスからもアクセス可能です。

---

# 🛠️ 開発者・講義向け資料   (Hack Guide)

このアプリを改造したい人向けのガイドです。
NotionとAIをつなぐ「ステートレス」なアーキテクチャを採用しています。

## 1. アプリケーション概要 (Overview)
- **役割**: Notionを記憶媒体とするAI秘書
- **アーキテクチャ**:
  `Frontend (ブラウザ)` ↔ `Backend (FastAPI)` ↔ `External (Notion / Gemini)`
- **データ保存**: アプリ自体はデータベースを持ちません。すべてのデータはブラウザやNotionに保存されます。

## 2. ディレクトリ構造 (Map)
改造するファイルを探すための地図です。

```text
memo_ai/
├── public/          (見た目と動き：フロントエンド)
│   ├── index.html   (骨組み：画面のレイアウト)
│   ├── style.css    (お化粧：色や配置のデザイン)
│   └── script.js    (動き：AIへの送信、Notionへの保存処理)
│
├── api/             (頭脳と連携：バックエンド)
│   ├── index.py     (指令塔：APIエンドポイントの定義)
│   ├── ai.py        (脳みそ：AIプロンプトと連携処理)
│   ├── notion.py    (手足：Notion APIとの通信)
│   └── config.py    (設定：モデル定義など)
│
└── .env             (秘密鍵：APIキーなどのパスワード類)
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
