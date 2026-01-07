"""
Application Configuration
Manages environment variables and default settings
"""
import os
from typing import Optional

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Notion Configuration
NOTION_API_KEY = os.getenv("NOTION_API_KEY")
NOTION_ROOT_PAGE_ID = os.getenv("NOTION_ROOT_PAGE_ID")

# AI Provider API Keys
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# Vertex AI Configuration (requires service account JSON)
GOOGLE_APPLICATION_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
VERTEX_AI_PROJECT = os.getenv("VERTEX_AI_PROJECT")
VERTEX_AI_LOCATION = os.getenv("VERTEX_AI_LOCATION", "us-central1")

# Default Models
# テキストのみの場合のデフォルト（API制限が緩い）
DEFAULT_TEXT_MODEL = os.getenv("DEFAULT_TEXT_MODEL", "gemini/gemini-2.0-flash-exp")

# マルチモーダル（画像あり）の場合のデフォルト
DEFAULT_MULTIMODAL_MODEL = os.getenv("DEFAULT_MULTIMODAL_MODEL", "gemini/gemini-2.0-flash-exp")

# LiteLLM Settings
LITELLM_VERBOSE = os.getenv("LITELLM_VERBOSE", "False").lower() == "true"
LITELLM_TIMEOUT = int(os.getenv("LITELLM_TIMEOUT", "30"))
LITELLM_MAX_RETRIES = int(os.getenv("LITELLM_MAX_RETRIES", "1"))

def get_api_key_for_provider(provider: str) -> Optional[str]:
    """
    Returns the API key or credential path for a given provider.
    
    Args:
        provider: LiteLLM provider name (e.g., "gemini", "vertex_ai", "openai")
    
    Returns:
        API key/credential string or None if not configured
    """
    provider_map = {
        "gemini": GEMINI_API_KEY,
        "google": GEMINI_API_KEY,  # Alias for Gemini API
        "vertex_ai": GOOGLE_APPLICATION_CREDENTIALS,  # Vertex AI uses service account
        "vertex_ai-vision": GOOGLE_APPLICATION_CREDENTIALS,
        "openai": OPENAI_API_KEY,
        "azure": os.getenv("AZURE_API_KEY"),
        "anthropic": ANTHROPIC_API_KEY,
    }
    return provider_map.get(provider.lower())

def is_provider_available(provider: str) -> bool:
    """
    Checks if a provider has configured credentials.
    
    For Gemini API: Checks GEMINI_API_KEY
    For Vertex AI: Checks GOOGLE_APPLICATION_CREDENTIALS and VERTEX_AI_PROJECT
    For others: Checks respective API keys
    """
    # Special handling for Vertex AI (needs both credentials and project)
    if provider.lower() in ["vertex_ai", "vertex_ai-vision"]:
        return bool(GOOGLE_APPLICATION_CREDENTIALS and VERTEX_AI_PROJECT)
    
    # For other providers, just check if API key exists
    return get_api_key_for_provider(provider) is not None
