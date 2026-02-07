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
    DEFAULT_MULTIMODAL_MODEL,
)
from api.logger import setup_logger

logger = setup_logger(__name__)

# モデルレジストリのキャッシュ (初回構築後に再利用)
_MODEL_CACHE = None
# プロバイダーごとの初期化エラーを保持
_PROVIDER_ERRORS = {}

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
    "gemini/gemini-flash-latest",  # 最新Flash（Gemini 3へのエイリアス）
    "gemini/gemini-pro-latest",  # 最新Pro（Gemini 3へのエイリアス）
    "gemini/gemini-2.5-flash",  # Gemini 2.5 Flash（2026/6まで）
    "gemini/gemini-2.5-pro",  # Gemini 2.5 Pro（2026/6まで）
    # OpenAI - 推奨
    "gpt-4o",  # GPT-4 Omni
    "gpt-4o-mini",  # 軽量版GPT-4o
    "gpt-4-turbo",  # GPT-4 Turbo
    "o1-mini",  # o1シリーズ軽量版
    "o3-mini",  # o3シリーズ軽量版
    # Anthropic - 推奨
    "claude-3-5-sonnet-20241022",  # Claude 3.5 Sonnet
    "claude-3-5-haiku-20241022",  # Claude 3.5 Haiku
    "claude-3-opus-20240229",  # Claude 3 Opus
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
    # LiteLLMが持つ全モデルのメタデータ（コスト、プロバイダー情報など）を一度だけ取得
    model_cost_map = litellm.model_cost

    # ===== Gemini: 動的取得（ベストプラクティス対応） =====
    gemini_loaded_dynamically = False
    try:
        from api.model_discovery import get_gemini_models

        # Gemini APIから取得（内部でキャッシング、リトライ、レート制限対応）
        gemini_models = get_gemini_models()

        if gemini_models and len(gemini_models) > 0:
            # Enrich Gemini models with pricing data from LiteLLM while preserving all other fields
            for gemini_model in gemini_models:
                model_id = gemini_model.get("id", "")
                # Try to find pricing data in LiteLLM's cost map
                if model_id in model_cost_map:
                    cost_info = model_cost_map[model_id]
                    input_cost = cost_info.get("input_cost_per_token", 0.0)
                    output_cost = cost_info.get("output_cost_per_token", 0.0)

                    # 価格情報の更新
                    gemini_model["cost_per_1k_tokens"] = {
                        "input": input_cost * 1000 if input_cost else 0.0,
                        "output": output_cost * 1000 if output_cost else 0.0,
                    }

                    # 重要: litellmのmode="image_generation"モデルはJSON非対応
                    # model_discoveryの名前ベース検出で漏れた場合の補正
                    if cost_info.get("mode") == "image_generation":
                        gemini_model["supports_json"] = False
                        logger.debug(
                            "Detected image_generation model '%s', setting supports_json=False",
                            model_id,
                        )

            registry.extend(gemini_models)
            gemini_loaded_dynamically = True
            _PROVIDER_ERRORS.pop("gemini", None)  # Clear error on success
            logger.info(
                "✅ Added %d Gemini models from dynamic API (pricing enriched)",
                len(gemini_models),
            )
        else:
            logger.warning("No Gemini models returned from API")
            gemini_loaded_dynamically = False
            _PROVIDER_ERRORS["gemini"] = "No models returned from API"

    except ImportError as e:
        logger.error("❌ CRITICAL: google-genai package not installed: %s", e)
        logger.error("⚠️  Install with: pip install -U google-genai")
        logger.error("⚠️  Or run: pip install -r requirements.txt")
        gemini_loaded_dynamically = False
        _PROVIDER_ERRORS["gemini"] = f"Package missing: {e}"

    except Exception as e:
        logger.warning(
            "Dynamic Gemini model loading failed: %s: %s", type(e).__name__, e
        )
        logger.info("Falling back to static model list")
        gemini_loaded_dynamically = False
        # Capture actual error
        _PROVIDER_ERRORS["gemini"] = str(e)

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
            _PROVIDER_ERRORS.pop("openai", None)  # Clear error on success
            logger.info(
                "✅ Added %d OpenAI models from dynamic API", len(openai_models)
            )
        else:
            # APIキーなしの場合は静的リストにフォールバック
            logger.info("No OpenAI models from API (static list will be used)")
            openai_loaded_dynamically = False
            _PROVIDER_ERRORS["openai"] = "No models returned from API (Check API Key)"

    except ImportError as e:
        logger.warning("openai package not installed: %s", e)
        logger.info("Install with: pip install -U openai")
        openai_loaded_dynamically = False
        _PROVIDER_ERRORS["openai"] = f"Package missing: {e}"

    except Exception as e:
        logger.warning(
            "Dynamic OpenAI model loading failed: %s: %s", type(e).__name__, e
        )
        logger.info("Falling back to static model list")
        openai_loaded_dynamically = False
        # Capture actual error
        _PROVIDER_ERRORS["openai"] = str(e)

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

    # 重複チェック用のセット（正規化名を記録）
    seen_models = set()  # モデルID重複チェック用（正規化された名前で管理）

    for model_id, model_info in model_cost_map.items():
        # Geminiモデルは動的取得できた場合のみスキップ
        if gemini_loaded_dynamically and (
            model_id.startswith("gemini/") or "gemini" in model_id.lower()
        ):
            continue

        # OpenAIモデルは動的取得できた場合のみスキップ
        # gpt-*, o1-*, o3-*, o4-*, chatgpt-* を全てスキップ
        if openai_loaded_dynamically:
            openai_prefixes = ["openai/", "gpt", "o1-", "o3-", "o4-", "chatgpt-"]
            if any(
                model_id.startswith(prefix) or model_id.lower().startswith(prefix)
                for prefix in openai_prefixes
            ):
                continue
            if "openai" in model_id.lower():
                continue

        # Geminiの古いバージョン（1.5/2.0）は常に除外
        if "gemini-1.5" in model_id or "gemini-2.0" in model_id:
            continue

        # チャット以外のモデルを除外（moderation、embedding等）
        non_chat_patterns = [
            "moderation",  # text-moderation-*, omni-moderation-*
            "embedding",  # text-embedding-*
            "whisper",  # 音声認識
            "tts",  # 音声合成
            "dall-e",  # 画像生成
        ]
        if any(pattern in model_id.lower() for pattern in non_chat_patterns):
            continue

        # モデル名を正規化（プレフィックスを除去）して重複チェック
        # 例: "openai/gpt-4" -> "gpt-4"
        normalized_name = model_id.split("/")[-1]

        # 重複チェック（同じ正規化名は1度のみ登録）
        if normalized_name in seen_models:
            continue
        seen_models.add(normalized_name)

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
                "claude-3-haiku",
                "claude-3-5-haiku",
                "gemini-flash",
                "gemini-pro-vision",
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
                "output": output_cost * 1000 if output_cost else 0.0,
            },
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
                # 1. モデルIDがRECOMMENDED_MODELSに完全一致
                # 2. モデル名（プレフィックスなし）がRECOMMENDED_MODELSに一致
                # 3. APIが recommended=True を返している
                model_id = model["id"]
                model_name = model.get("name", "")
                is_in_recommended_list = (
                    model_id in RECOMMENDED_MODELS or model_name in RECOMMENDED_MODELS
                )
                api_recommends = model.get("recommended", False)

                if is_in_recommended_list or api_recommends:
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
    user_selection: Optional[str] = None,
    image_generation: bool = False,
) -> str:
    """
    入力タイプに基づいて最適なモデルをインテリジェントに選択します。

    選択ロジック:
    1. ユーザーが明示的にモデルを選択している場合、それを最優先します。
    2. 画像生成が要求されている場合、画像生成対応モデルの中から選択します。
    3. 画像入力がある場合、Vision対応モデルの中から選択します。
    4. テキストのみの場合、テキストモデル（またはデフォルト）を使用します。

    Args:
        has_image: 画像データが含まれているかどうか
        user_selection: ユーザーがフロントエンドで選択したモデルID (任意)
        image_generation: 画像生成が必要かどうか

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
                logger.warning(
                    "Selected model '%s' does not support images. This request may fail.",
                    user_selection,
                )
            return user_selection
        else:
            logger.warning(
                "Selected model '%s' is not available. Falling back to default.",
                user_selection,
            )

    # 優先度2: 入力タイプに基づく自動選択
    if image_generation:
        # 画像生成モデルが必要です

        # フォールバック候補リスト（優先順）
        FALLBACK_IMAGE_GEN_MODELS = [
            "gemini/gemini-2.5-flash-image",
            "openai/dall-e-3",
            "openai/dall-e-2",
        ]

        image_gen_models = get_image_generation_models()
        if image_gen_models:
            image_gen_model_ids = [m["id"] for m in image_gen_models]

            # フォールバックリスト順に利用可能なモデルを探す
            for fallback_model in FALLBACK_IMAGE_GEN_MODELS:
                if fallback_model in image_gen_model_ids:
                    logger.info("Using image generation model '%s'", fallback_model)
                    return fallback_model

            # フォールバックが見つからない場合、利用可能な最初の画像生成モデルを使用
            logger.info(
                "Using first available image generation model '%s'",
                image_gen_models[0]["id"],
            )
            return image_gen_models[0]["id"]
        else:
            raise RuntimeError(
                "画像生成に対応したモデルが利用できません。APIキーの設定を確認してください。"
            )

    if has_image:
        # 画像入力を処理できるVisionモデルが必要です

        # フォールバック候補リスト（優先順）
        FALLBACK_VISION_MODELS = [
            DEFAULT_MULTIMODAL_MODEL,
            "gemini/gemini-2.5-flash",
            "openai/gpt-4o-mini",
        ]

        vision_models = get_models_by_capability(supports_vision=True)
        if vision_models:
            vision_model_ids = [m["id"] for m in vision_models]

            # フォールバックリスト順に利用可能なモデルを探す
            for fallback_model in FALLBACK_VISION_MODELS:
                if fallback_model in vision_model_ids:
                    if fallback_model != DEFAULT_MULTIMODAL_MODEL:
                        logger.info(
                            "Using fallback vision model '%s' (default '%s' not available)",
                            fallback_model,
                            DEFAULT_MULTIMODAL_MODEL,
                        )
                    return fallback_model

            # フォールバックが見つからない場合、利用可能な最初のVisionモデルを使用
            logger.info(
                "Using first available vision model '%s'", vision_models[0]["id"]
            )
            return vision_models[0]["id"]
        else:
            raise RuntimeError(
                "画像認識に対応したモデルが利用できません。APIキーの設定を確認してください。"
            )

    else:
        # テキストのみの入力

        # フォールバック候補リスト（安定性の高いモデル順）
        FALLBACK_TEXT_MODELS = [
            DEFAULT_TEXT_MODEL,
            "gemini/gemini-2.5-flash",
            "openai/gpt-4o-mini",
        ]

        # 1. フォールバックリスト順に試行
        available_ids = [m["id"] for m in get_available_models()]
        for fallback_model in FALLBACK_TEXT_MODELS:
            if fallback_model in available_ids:
                if fallback_model != DEFAULT_TEXT_MODEL:
                    logger.info(
                        "Using fallback model '%s' (default '%s' not available)",
                        fallback_model,
                        DEFAULT_TEXT_MODEL,
                    )
                return fallback_model

        # 2. フォールバックがない場合、テキスト専用モデルを優先して選択
        # 単価が安い傾向があるため
        text_models = get_models_by_capability(supports_vision=False)
        if text_models:
            logger.info("Using first available text model '%s'", text_models[0]["id"])
            return text_models[0]["id"]

        # 3. 最終手段: 何でもいいので利用可能なモデルを使用
        if available_ids:
            logger.info("Using first available model '%s'", available_ids[0])
            return available_ids[0]
        else:
            raise RuntimeError(
                "利用可能なAIモデルがありません。APIキーの設定を確認してください。"
            )


def check_default_model_availability(model_id: str) -> Dict[str, Any]:
    """
    デフォルトモデルが実際に利用可能かチェック

    Returns:
        {
            "available": bool,
            "error": str | None  # 実際のエラーメッセージ
        }
    """
    if not model_id:
        return {"available": False, "error": "Model not specified"}

    # モデルがレジストリに存在するか
    metadata = get_model_metadata(model_id)
    if not metadata:
        return {"available": False, "error": "Model not found in registry"}

    # プロバイダーが利用可能か
    provider = metadata.get("litellm_provider")
    if not provider or not is_provider_available(provider):
        return {"available": False, "error": "API key not configured"}

    # プロバイダー側でエラーが発生しているか
    if provider in _PROVIDER_ERRORS:
        return {"available": False, "error": _PROVIDER_ERRORS[provider]}

    return {"available": True, "error": None}


# フロントエンド向けのコンビニエンス関数
def get_text_models() -> List[Dict[str, Any]]:
    """利用可能なテキスト専用モデルのリストを返します"""
    return get_models_by_capability(supports_vision=False)


def get_vision_models() -> List[Dict[str, Any]]:
    """利用可能なVision対応モデルのリストを返します"""
    return get_models_by_capability(supports_vision=True)


def get_image_generation_models() -> List[Dict[str, Any]]:
    """利用可能な画像生成対応モデルのリストを返します"""
    models = get_available_models()
    return [m for m in models if m.get("supports_image_generation", False)]
