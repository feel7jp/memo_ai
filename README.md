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






curl -s https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json | head -100
    {
      "id": "gemini/gemini-1.5-pro",
      "name": "Gemini 1.5 Pro",
      "provider": "Google",
      "supports_vision": true,
      "supports_json": true,
      "cost_per_1k_tokens": {
        "input": 0.00125,
        "output": 0.005
      }
    },
    {
      "id": "gemini/gemini-2.0-flash",
      "name": "Gemini 2.0 Flash",
      "provider": "Google",
      "supports_vision": true,
      "supports_json": true,
      "cost_per_1k_tokens": {
        "input": 0.000075,
        "output": 0.0003
      }
    },




https://aistudio.google.com/usage
Gemini API のレート制限 無料枠
モデル,カテゴリ,RPM_使用量,RPM_上限,TPM_使用量,TPM_上限,RPD_使用量,RPD_上限
gemini-2.5-flash,テキスト出力モデル,5,5,2410,250000,23,20
gemma-3-27b,その他のモデル,2,30,826,15000,2,14400
gemini-2.5-flash-lite,テキスト出力モデル,0,10,0,250000,0,20
gemini-2.5-flash-tts,マルチモーダル生成モデル,0,3,0,10000,0,10
gemini-3-flash,テキスト出力モデル,0,5,0,250000,0,20
gemini-robotics-er-1.5-preview,その他のモデル,0,10,0,250000,0,20
gemma-3-12b,その他のモデル,0,30,0,15000,0,14400
gemma-3-1b,その他のモデル,0,30,0,15000,0,14400
gemma-3-2b,その他のモデル,0,30,0,15000,0,14400
gemma-3-4b,その他のモデル,0,30,0,15000,0,14400
gemini-embedding-1.0,その他のモデル,0,100,0,30000,0,1000
gemini-2.5-flash-native-audio-dialog,Live API,0,無制限,0,1000000,0,無制限
