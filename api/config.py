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

# --- Notion設定 (Notion Configuration) ---
# Notion APIへのアクセスと、データ保存先のルートページID
NOTION_API_KEY = os.getenv("NOTION_API_KEY")
NOTION_ROOT_PAGE_ID = os.getenv("NOTION_ROOT_PAGE_ID")

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
DEFAULT_TEXT_MODEL = os.getenv("DEFAULT_TEXT_MODEL", "gemini/gemini-2.0-flash-exp")

# 画像を含むマルチモーダル入力の場合のデフォルト（Vision対応モデル必須）
DEFAULT_MULTIMODAL_MODEL = os.getenv("DEFAULT_MULTIMODAL_MODEL", "gemini/gemini-2.0-flash-exp")

# --- LiteLLM設定 (LiteLLM Settings) ---
# LLM呼び出しライブラリ `litellm` の動作設定
LITELLM_VERBOSE = os.getenv("LITELLM_VERBOSE", "False").lower() == "true" # 詳細ログ出力
LITELLM_TIMEOUT = int(os.getenv("LITELLM_TIMEOUT", "30")) # タイムアウト時間（秒）
LITELLM_MAX_RETRIES = int(os.getenv("LITELLM_MAX_RETRIES", "1")) # 最大再試行回数

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
