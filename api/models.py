"""
AI Model Definitions and Selection Logic
AIモデルのメタデータ管理とインテリジェントな自動選択ロジックを提供します。
LiteLLMから利用可能なモデル情報を動的に取得し、APIキーの設定状況に基づいて
実際に使用可能なモデルをフィルタリングします。
"""
from typing import List, Dict, Any, Optional
import litellm
from api.config import (
    is_provider_available,
    DEFAULT_TEXT_MODEL,
    DEFAULT_MULTIMODAL_MODEL
)

# モデルレジストリのキャッシュ (初回構築後に再利用)
_MODEL_CACHE = None

def _build_model_registry() -> List[Dict[str, Any]]:
    """
    LiteLLMの `model_cost` 辞書からモデルレジストリを構築します。
    プロバイダーの種類（Gemini API vs Vertex AIなど）を自動検出し、
    フロントエンドで表示しやすい形式に整形します。
    """
    registry = []
    
    # LiteLLMが持つ全モデルのメタデータ（コスト、プロバイダー情報など）を取得
    model_cost_map = litellm.model_cost
    
    # プロバイダー表示名のマッピング
    # 内部IDをユーザーフレンドリーな名称に変換します。
    PROVIDER_DISPLAY_NAMES = {
        "gemini": "Gemini API",
        "vertex_ai": "Vertex AI", 
        "vertex_ai-vision": "Vertex AI",
        "google": "Gemini API",
        "openai": "OpenAI",
        "azure": "Azure OpenAI",
        "anthropic": "Anthropic",
    }
    
    # LiteLLMのレジストリに含まれる全モデルを走査
    for model_id, model_info in model_cost_map.items():
        # メタデータからプロバイダーIDを取得
        litellm_provider = model_info.get("litellm_provider")
        
        # メタデータにない場合、モデルIDからプロバイダーを推測
        if not litellm_provider:
            if model_id.startswith("gemini/"):
                litellm_provider = "gemini"
            elif model_id.startswith("vertex_ai/"):
                litellm_provider = "vertex_ai"
            elif model_id.startswith("openai/") or model_id.startswith("gpt"):
                litellm_provider = "openai"
            elif model_id.startswith("anthropic/") or model_id.startswith("claude"):
                litellm_provider = "anthropic"
            else:
                # 未知のプロバイダーはスキップ
                continue
        
        # 表示名が定義されている主要プロバイダーのみリストに含める
        if litellm_provider not in PROVIDER_DISPLAY_NAMES:
            continue
        
        provider_display = PROVIDER_DISPLAY_NAMES[litellm_provider]
        
        # Vision（画像認識）機能の対応可否を判定
        supports_vision = model_info.get("supports_vision", False)
        
        # LiteLLMのメタデータで判定できない場合のフォールバック（モデル名パターンマッチング）
        if not supports_vision:
            vision_patterns = [
                "gpt-4o", "gpt-4-vision",
                "claude-3", "claude-3-5-sonnet",
                "gemini-1.5", "gemini-2.0", "gemini-pro-vision"
            ]
            for pattern in vision_patterns:
                if pattern in model_id.lower():
                    supports_vision = True
                    break
        
        # JSONモードのサポート（最近のモデルはほぼサポート）
        supports_json = model_info.get("supports_response_schema", True)
        
        # コスト情報の取得（トークン単価）
        input_cost = model_info.get("input_cost_per_token", 0.0)
        output_cost = model_info.get("output_cost_per_token", 0.0)
        
        # レジストリエントリの作成
        entry = {
            "id": model_id,
            "name": model_id.split("/")[-1],  # "gemini/gemini-pro" -> "gemini-pro"
            "provider": provider_display,  # 表示用プロバイダー名
            "litellm_provider": litellm_provider,  # ルーティング用プロバイダーID
            "supports_vision": supports_vision,
            "supports_json": supports_json,
            "cost_per_1k_tokens": {
                "input": input_cost * 1000 if input_cost else 0.0,
                "output": output_cost * 1000 if output_cost else 0.0
            }
        }
        
        # レートリミット情報の保持（もしあれば）
        if "rate_limit_note" in model_info:
            entry["rate_limit_note"] = model_info["rate_limit_note"]
        
        registry.append(entry)
    
    # UI表示順序の調整: プロバイダー名 > モデル名でソート
    registry.sort(key=lambda x: (x["provider"], x["name"]))
    
    return registry

def get_model_registry() -> List[Dict[str, Any]]:
    """
    モデルレジストリを返します。初回呼び出し時に構築を行い、以降はキャッシュを返します。
    """
    global _MODEL_CACHE
    if _MODEL_CACHE is None:
        _MODEL_CACHE = _build_model_registry()
    return _MODEL_CACHE





def get_available_models() -> List[Dict[str, Any]]:
    """
    設定されているAPIキー/認証情報に基づいて、現在利用可能なモデルのリストを返します。
    `api.config.is_provider_available` を使用して、各モデルのプロバイダーが有効かチェックします。
    """
    available = []
    registry = get_model_registry()
    
    for model in registry:
        # LiteLLMのプロバイダーID (litellm_provider) を使用して認証チェックを行う
        # 表示名 (provider) ではなく、実際のバックエンド識別子を使用する必要があります。
        litellm_provider = model.get("litellm_provider")
        
        if litellm_provider and is_provider_available(litellm_provider):
            available.append(model)
    
    return available

def get_models_by_capability(supports_vision: bool = None) -> List[Dict[str, Any]]:
    """
    利用可能なモデルを機能（Vision対応など）でフィルタリングして返します。
    
    Args:
        supports_vision: 
            True  -> Vision対応モデルのみ
            False -> テキスト専用モデルのみ
            None  -> 全ての利用可能なモデル
    
    Returns:
        フィルタリングされたモデルのメタデータリスト
    """
    models = get_available_models()
    
    if supports_vision is None:
        return models
    
    return [m for m in models if m.get("supports_vision") == supports_vision]


def get_model_metadata(model_id: str) -> Optional[Dict[str, Any]]:
    """
    特定のモデルIDに対応するメタデータを取得します。
    選択されたモデルの機能確認やコスト計算に使用されます。
    
    Args:
        model_id: モデル識別子 (例: "gemini/gemini-2.0-flash-exp")
    
    Returns:
        モデル情報の辞書、または見つからない場合はNone
    """
    registry = get_model_registry()
    for model in registry:
        if model["id"] == model_id:
            return model
    return None



def select_model_for_input(
    has_image: bool = False,
    user_selection: Optional[str] = None
) -> str:
    """
    入力タイプに基づいて最適なモデルをインテリジェントに選択します。
    
    選択ロジック:
    1. ユーザーが明示的にモデルを選択している場合、それを最優先します。
    2. 画像入力がある場合、Vision対応モデルの中から選択します。
    3. テキストのみの場合、テキストモデル（またはデフォルト）を使用します。
    
    Args:
        has_image: 画像データが含まれているかどうか
        user_selection: ユーザーがフロントエンドで選択したモデルID (任意)
    
    Returns:
        使用すべきモデルID
    """
    # 優先度1: ユーザーの明示的な選択
    if user_selection:
        # 選択されたモデルが現在有効か検証
        metadata = get_model_metadata(user_selection)
        if metadata and is_provider_available(metadata["litellm_provider"]):
            # テキスト専用モデルに画像を送ろうとしている場合は警告を出しますが、ユーザーの意思を尊重します。
            if has_image and not metadata.get("supports_vision"):
                print(f"WARNING: Selected model '{user_selection}' does not support images. "
                      f"This request may fail.")
            return user_selection
        else:
            print(f"WARNING: Selected model '{user_selection}' is not available. "
                  f"Falling back to default.")
    
    # 優先度2: 入力タイプに基づく自動選択
    if has_image:
        # 画像入力を処理できるVisionモデルが必要です
        
        # フォールバック候補リスト（優先順）
        FALLBACK_VISION_MODELS = [
            DEFAULT_MULTIMODAL_MODEL,
            "gemini/gemini-2.0-flash-exp",
            "gemini/gemini-1.5-flash",
            "gemini/gemini-1.5-pro",
            "openai/gpt-4o-mini",
            "openai/gpt-4o",
            "anthropic/claude-3-5-sonnet-20241022"
        ]
        
        vision_models = get_models_by_capability(supports_vision=True)
        if vision_models:
            vision_model_ids = [m["id"] for m in vision_models]
            
            # フォールバックリスト順に利用可能なモデルを探す
            for fallback_model in FALLBACK_VISION_MODELS:
                if fallback_model in vision_model_ids:
                    if fallback_model != DEFAULT_MULTIMODAL_MODEL:
                        print(f"INFO: Using fallback vision model '{fallback_model}' (default '{DEFAULT_MULTIMODAL_MODEL}' not available)")
                    return fallback_model
            
            # フォールバックが見つからない場合、利用可能な最初のVisionモデルを使用
            print(f"INFO: Using first available vision model '{vision_models[0]['id']}'")
            return vision_models[0]["id"]
        else:
            raise RuntimeError("画像認識に対応したモデルが利用できません。APIキーの設定を確認してください。")
    
    else:
        # テキストのみの入力
        
        # フォールバック候補リスト（安定性の高いモデル順）
        FALLBACK_TEXT_MODELS = [
            DEFAULT_TEXT_MODEL,
            "gemini/gemini-2.0-flash-exp",
            "gemini/gemini-1.5-flash",
            "gemini/gemini-1.5-pro",
            "openai/gpt-4o-mini",
            "anthropic/claude-3-5-haiku-20241022"
        ]
        
        # 1. フォールバックリスト順に試行
        available_ids = [m["id"] for m in get_available_models()]
        for fallback_model in FALLBACK_TEXT_MODELS:
            if fallback_model in available_ids:
                if fallback_model != DEFAULT_TEXT_MODEL:
                    print(f"INFO: Using fallback model '{fallback_model}' (default '{DEFAULT_TEXT_MODEL}' not available)")
                return fallback_model
            
        # 2. フォールバックがない場合、テキスト専用モデルを優先して選択
        # 単価が安い傾向があるため
        text_models = get_models_by_capability(supports_vision=False)
        if text_models:
            print(f"INFO: Using first available text model '{text_models[0]['id']}'")
            return text_models[0]["id"]
            
        # 3. 最終手段: 何でもいいので利用可能なモデルを使用
        if available_ids:
            print(f"INFO: Using first available model '{available_ids[0]}'")
            return available_ids[0]
        else:
            raise RuntimeError("利用可能なAIモデルがありません。APIキーの設定を確認してください。")


# フロントエンド向けのコンビニエンス関数
def get_text_models() -> List[Dict[str, Any]]:
    """利用可能なテキスト専用モデルのリストを返します"""
    return get_models_by_capability(supports_vision=False)


def get_vision_models() -> List[Dict[str, Any]]:
    """利用可能なVision対応モデルのリストを返します"""
    return get_models_by_capability(supports_vision=True)
