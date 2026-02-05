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

# 推奨モデルリスト（ホワイトリスト）
# フロントエンドUIに表示する厳選モデル
# 同一モデルの複数バージョン（日付付きバリアント等）を除外し、
# ユーザーが選びやすい主要モデルのみをリストアップ
# 実際に利用可能なモデルのみを含める（404エラー回避）
#
# 調査結果（2026-02-05）:
# - Gemini: -latest エイリアスを使用すると最新安定版にアクセス可能
# - gemini-flash-latest → Gemini 3 Flash (2026年1月21日以降)
# - gemini-pro-latest → Gemini 3 Pro (2026年1月21日以降)
# - Gemini 2.5シリーズは2026年6月17日に退役予定だが現在利用可能
RECOMMENDED_MODELS = [
    # Gemini API - 推奨（LiteLLMドキュメントで確認済み）
    "gemini/gemini-flash-latest",   # 最新Flash（Gemini 3へのエイリアス）
    "gemini/gemini-pro-latest",     # 最新Pro（Gemini 3へのエイリアス）  
    "gemini/gemini-2.5-flash",      # Gemini 2.5 Flash（2026/6まで）
    "gemini/gemini-2.5-pro",        # Gemini 2.5 Pro（2026/6まで）
    
    # OpenAI - 推奨
    "gpt-4o",           # GPT-4 Omni
    "gpt-4o-mini",      # 軽量版GPT-4o
    "gpt-4-turbo",      # GPT-4 Turbo
    "o1-mini",          # o1シリーズ軽量版
    "o3-mini",          # o3シリーズ軽量版
    
    # Anthropic - 推奨
    "claude-3-5-sonnet-20241022",  # Claude 3.5 Sonnet
    "claude-3-5-haiku-20241022",   # Claude 3.5 Haiku
    "claude-3-opus-20240229",      # Claude 3 Opus
]


def _build_model_registry() -> List[Dict[str, Any]]:
    """
    モデルレジストリを構築します。
    
    **動的モデル発見**: Gemini APIから直接取得（ベストプラクティス対応）
    - キャッシング: 1時間TTL
    - エラーハンドリング: 静的リストへのフォールバック
    - レート制限: 起動時1回のみ呼び出し
    """
    registry = []
    
    # ===== Gemini: 動的取得（ベストプラクティス対応） =====
    gemini_loaded_dynamically = False
    try:
        from api.model_discovery import get_gemini_models
        
        # Gemini APIから取得（内部でキャッシング、リトライ、レート制限対応）
        gemini_models = get_gemini_models()
        
        if gemini_models and len(gemini_models) > 0:
            registry.extend(gemini_models)
            gemini_loaded_dynamically = True
            print(f"[INFO] ✅ Added {len(gemini_models)} Gemini models from dynamic API")
        else:
            print(f"[WARNING] No Gemini models returned from API")
            gemini_loaded_dynamically = False
            
    except ImportError as e:
        print(f"[WARNING] google-genai package not installed: {e}")
        print(f"[INFO] Install with: pip install -U google-genai")
        gemini_loaded_dynamically = False
        
    except Exception as e:
        print(f"[WARNING] Dynamic Gemini model loading failed: {type(e).__name__}: {e}")
        print(f"[INFO] Falling back to static model list")
        gemini_loaded_dynamically = False
    
    # ===== OpenAI: 動的取得（ベストプラクティス対応） =====
    openai_loaded_dynamically = False
    try:
        from api.model_discovery import get_openai_models
        
        # OpenAI APIから取得（内部でキャッシング）
        # APIキーがない場合は空リストを返す
        openai_models = get_openai_models()
        
        if openai_models and len(openai_models) > 0:
            registry.extend(openai_models)
            openai_loaded_dynamically = True
            print(f"[INFO] ✅ Added {len(openai_models)} OpenAI models from dynamic API")
        else:
            # APIキーなしの場合は静的リストにフォールバック
            print(f"[INFO] No OpenAI models from API (static list will be used)")
            openai_loaded_dynamically = False
            
    except ImportError as e:
        print(f"[WARNING] openai package not installed: {e}")
        print(f"[INFO] Install with: pip install -U openai")
        openai_loaded_dynamically = False
        
    except Exception as e:
        print(f"[WARNING] Dynamic OpenAI model loading failed: {type(e).__name__}: {e}")
        print(f"[INFO] Falling back to static model list")
        openai_loaded_dynamically = False
    

    # LiteLLMが持つ全モデルのメタデータ（コスト、プロバイダー情報など）を取得
    model_cost_map = litellm.model_cost
    
    # プロバイダー表示名のマッピング
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
    seen_models = {}  # モデルID重複チェック用（正規化された名前で管理）
    
    for model_id, model_info in model_cost_map.items():
        # Geminiモデルは動的取得できた場合のみスキップ
        if gemini_loaded_dynamically and (model_id.startswith("gemini/") or "gemini" in model_id.lower()):
            continue
        
        # OpenAIモデルは動的取得できた場合のみスキップ
        if openai_loaded_dynamically and (model_id.startswith("openai/") or model_id.startswith("gpt") or "openai" in model_id.lower()):
            continue
        
        # Geminiの古いバージョン（1.5/2.0）は常に除外
        if "gemini-1.5" in model_id or "gemini-2.0" in model_id:
            continue
        
        # モデル名を正規化（プレフィックスを除去）して重複チェック
        # 例: "openai/gpt-4" -> "gpt-4"
        normalized_name = model_id.split("/")[-1]
        
        # 重複チェック: 既に同じ正規化名のモデルが登録されていればスキップ
        if normalized_name in seen_models:
            continue
            
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
        # コスト最適化のため、安価なflash系モデルのみをvision対応として認識
        if not supports_vision:
            vision_patterns = [
                "gpt-4o-mini",
                "claude-3-haiku", "claude-3-5-haiku",
                "gemini-flash", "gemini-pro-vision"
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
            "name": normalized_name,  # 正規化された名前を使用
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
        seen_models[normalized_name] = True  # 重複チェック用に正規化名を記録
    
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





def get_available_models(recommended_only: bool = True) -> List[Dict[str, Any]]:
    """
    設定されているAPIキー/認証情報に基づいて、現在利用可能なモデルのリストを返します。
    `api.config.is_provider_available` を使用して、各モデルのプロバイダーが有効かチェックします。
    
    Args:
        recommended_only: 
            True  -> 推奨モデルのみ（RECOMMENDED_MODELSホワイトリスト）
            False -> 全モデル（デバッグ用）
    """
    available = []
    registry = get_model_registry()
    
    for model in registry:
        # LiteLLMのプロバイダーID (litellm_provider) を使用して認証チェックを行う
        # 表示名 (provider) ではなく、実際のバックエンド識別子を使用する必要があります。
        litellm_provider = model.get("litellm_provider")
        
        if litellm_provider and is_provider_available(litellm_provider):
            # 推奨モデルフィルター
            if recommended_only:
                if model["id"] in RECOMMENDED_MODELS:
                    available.append(model)
            else:
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
            "gemini/gemini-2.5-flash",
            "openai/gpt-4o-mini"
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
            "gemini/gemini-2.5-flash",
            "openai/gpt-4o-mini"
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
