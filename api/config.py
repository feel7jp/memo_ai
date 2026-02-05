"""
Application Configuration
アプリケーション全体の設定と環境変数を管理します。
Notion APIや各種AIプロバイダー（Gemini, OpenAI, Anthropic等）の認証情報、
およびデフォルトモデルの設定を集約しています。
"""

import os
from typing import Optional

# 環境変数の読み込み (Load environment variables)
# .envファイルが存在する場合、そこから環境変数をロードします。
# これにより、開発環境での設定管理が容易になります。
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


# ヘルパー関数: Notion ID正規化（1行版）
def normalize_notion_id(notion_id_or_url: str) -> str:
    """Notion IDまたはURLを32文字の英数字に正規化"""
    import re

    return (
        re.sub(
            r"[^a-zA-Z0-9]",
            "",
            notion_id_or_url.split("/")[-1].split("?")[0].split("#")[0],
        )[-32:]
        if notion_id_or_url
        else ""
    )


# --- Notion設定 (Notion Configuration) ---
# Notion APIへのアクセスと、データ保存先のルートページID
NOTION_API_KEY = os.getenv("NOTION_API_KEY")
_raw_page_id = os.getenv("NOTION_ROOT_PAGE_ID")
NOTION_ROOT_PAGE_ID = normalize_notion_id(_raw_page_id) if _raw_page_id else None

# --- AIプロバイダー APIキー (AI Provider API Keys) ---
# 各種LLMプロバイダーのAPIキー。使用しないプロバイダーは未設定で構いません。
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# --- Vertex AI設定 (Vertex AI Configuration) ---
# Google Cloud PlatformのVertex AIを使用する場合の設定
# サービスアカウントJSONファイルのパスとプロジェクトIDが必要です。
GOOGLE_APPLICATION_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
VERTEX_AI_PROJECT = os.getenv("VERTEX_AI_PROJECT")
VERTEX_AI_LOCATION = os.getenv("VERTEX_AI_LOCATION", "us-central1")

# --- デフォルトモデル設定 (Default Models) ---
# ユーザーがモデルを選択していない場合に使用されるデフォルトモデル
# 環境変数でオーバーライド可能です。

# テキストのみの場合のデフォルト（高速・安価なモデルを推奨）
DEFAULT_TEXT_MODEL = os.getenv("DEFAULT_TEXT_MODEL", "gemini/gemini-2.5-flash")

# 画像を含むマルチモーダル入力の場合のデフォルト（Vision対応モデル必須）
DEFAULT_MULTIMODAL_MODEL = os.getenv(
    "DEFAULT_MULTIMODAL_MODEL", "gemini/gemini-2.5-flash"
)

# --- デバッグモード設定 (Debug Mode) ---
# デバッグエンドポイントとAIモデル選択機能を有効にします。
# 本番環境では必ず False に設定してください。
DEBUG_MODE = os.getenv("DEBUG_MODE", "false").lower() == "true"

# --- デフォルトシステムプロンプト (Default System Prompt) ---
# AIの基本的な役割定義。ターゲットごとに上書き可能です。
# 環境変数でオーバーライド可能です。
DEFAULT_SYSTEM_PROMPT = os.getenv(
    "DEFAULT_SYSTEM_PROMPT",
    """優秀な秘書として、参考情報を参照しながら、ユーザーの意図を予測し、以下のルールに従い柔軟に考えて返答すること。

- 【質問の場合、回答する】
    - 参照コンテキストから回答できる場合は秘書として柔軟に回答する
    - 例: 今日の予定は？→ 予定を回答
- 【回答できない場合、タスク名に変換】
    - 先頭に適切な絵文字を追加
    - 動詞で終わる明確なタスク名にする
    - 返答はタスク名のみ。説明や会話は不要。
- 【画像の場合】
    - 画像の内容からユーザーの意図を深く推定し、画像からタスク名を生成""",
)


# --- 環境変数の検証 (Environment Variable Validation) ---
def _validate_env_var(var_name: str, var_value: str) -> None:
    """環境変数の値が正しい形式かチェック"""
    if not var_value:
        return

    # スペースチェック
    if var_value != var_value.strip():
        print(
            f"⚠️  [{var_name}] 不要なスペースあり → .envで '{var_name}={var_value.strip()}' に修正してください"
        )


# デフォルトモデルの検証
_validate_env_var("DEFAULT_TEXT_MODEL", DEFAULT_TEXT_MODEL)
_validate_env_var("DEFAULT_MULTIMODAL_MODEL", DEFAULT_MULTIMODAL_MODEL)

# --- LiteLLM設定 (LiteLLM Settings) ---
# LLM呼び出しライブラリ `litellm` の動作設定
LITELLM_VERBOSE = (
    os.getenv("LITELLM_VERBOSE", "False").lower() == "true"
)  # 詳細ログ出力
LITELLM_TIMEOUT = int(os.getenv("LITELLM_TIMEOUT", "30"))  # タイムアウト時間（秒）
LITELLM_MAX_RETRIES = int(os.getenv("LITELLM_MAX_RETRIES", "1"))  # 最大再試行回数


def get_api_key_for_provider(provider: str) -> Optional[str]:
    """
    指定されたプロバイダーに対応するAPIキーまたは認証情報パスを返します。

    Args:
        provider: LiteLLMのプロバイダー名 (例: "gemini", "vertex_ai", "openai")

    Returns:
        APIキー文字列、または設定されていない場合はNone
    """
    provider_map = {
        "gemini": GEMINI_API_KEY,
        "google": GEMINI_API_KEY,  # "google" は Gemini API のエイリアスとして扱います
        "vertex_ai": GOOGLE_APPLICATION_CREDENTIALS,  # Vertex AI はサービスアカウントJSONパスを使用
        "vertex_ai-vision": GOOGLE_APPLICATION_CREDENTIALS,
        "openai": OPENAI_API_KEY,
        "azure": os.getenv("AZURE_API_KEY"),
        "anthropic": ANTHROPIC_API_KEY,
    }
    return provider_map.get(provider.lower())


def is_provider_available(provider: str) -> bool:
    """
    指定されたプロバイダーの認証情報が設定されているか確認します。

    Gemini API: GEMINI_API_KEY の有無
    Vertex AI: 認証情報JSONパス と プロジェクトID の両方が必要
    その他: 各APIキーの有無
    """
    # Vertex AIの場合は特殊なチェック（クレデンシャル + プロジェクトID）
    if provider.lower() in ["vertex_ai", "vertex_ai-vision"]:
        return bool(GOOGLE_APPLICATION_CREDENTIALS and VERTEX_AI_PROJECT)

    # その他のプロバイダーはAPIキーの存在確認のみ
    return get_api_key_for_provider(provider) is not None
