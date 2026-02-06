"""
動的モデル発見モジュール
各プロバイダーAPIから実際に利用可能なモデルを取得し、キャッシュする
"""

import os
from typing import List, Dict, Any
from datetime import datetime, timedelta
from api.logger import setup_logger

logger = setup_logger(__name__)

# キャッシュ設定
_MODEL_CACHE: Dict[str, List[Dict[str, Any]]] = {}
_CACHE_EXPIRY: Dict[str, datetime] = {}
# 環境変数対応: MODEL_CACHE_TTLデフォルト3600秒（1時間）
CACHE_TTL = timedelta(seconds=int(os.getenv("MODEL_CACHE_TTL", "3600")))


def get_gemini_models() -> List[Dict[str, Any]]:
    """
    Gemini APIから実際に利用可能なモデル一覧を動的に取得

    ベストプラクティス対応 (2024):
    - キャッシング（1時間TTL）
    - エクスポネンシャルバックオフ（最大3回リトライ）
    - レート制限対応（起動時1回のみ）
    - モデルフィルタリング（supported_generation_methods）

    Returns:
        モデル情報のリスト。各モデルは以下の構造:
        {
            "id": "gemini/gemini-2.5-flash",
            "name": "gemini-2.5-flash",
            "provider": "Gemini API",
            "litellm_provider": "gemini",
            "supports_vision": True,
            "supports_json": True,
            "description": "...",
            "cost_per_1k_tokens": {"input": 0.0, "output": 0.0}
        }
    """
    cache_key = "gemini_models_v3"  # v3: 教育用非推奨モデル追加

    # キャッシュチェック
    if cache_key in _MODEL_CACHE:
        if datetime.now() < _CACHE_EXPIRY[cache_key]:
            cached_count = len(_MODEL_CACHE[cache_key])
            logger.info("💾 Using cached Gemini models (%d models)", cached_count)
            return _MODEL_CACHE[cache_key]

    # Gemini APIから取得（エクスポネンシャルバックオフ）
    try:
        # 新しいパッケージ: google-genai (2024+ recommended)
        import google.genai as genai
        import time

        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            logger.warning("GEMINI_API_KEY not set")
            return []

        max_retries = 3
        models = []

        for attempt in range(max_retries):
            try:
                # google-genai 新SDK（Client APIを使用）
                client = genai.Client(api_key=api_key)

                # client.models.list()でモデル一覧を取得（全モデル）
                #
                # ===== Gemini API レスポンスフォーマット (2024_12+) =====
                # 新SDKバージョンでは以下の属性が利用可能:
                # - name: モデルID (例: "models/gemini-2.5-flash")
                # - display_name: 表示名
                # - description: モデルの説明
                # - supported_actions: サポートされている機能のリスト (NEW)
                #   旧SDKでは supported_generation_methods
                #   例: ['generateContent', 'streamGenerateContent', ...]
                # - input_token_limit: 入力トークン制限
                # - output_token_limit: 出力トークン制限
                # - temperature, top_k, top_p: デフォルトパラメータ
                # - thinking: Thinking機能のサポート (一部モデルのみ)
                # - endpoints: 利用可能なエンドポイント
                # - labels: モデルのラベル・タグ
                # その他: checkpoints, tuned_model_info, default_checkpoint_id, etc.
                # =====================================================
                for model in client.models.list():
                    # 新SDKではsupported_actions、旧SDKではsupported_generation_methods
                    methods = getattr(model, "supported_actions", None)
                    if methods is None:
                        methods = getattr(model, "supported_generation_methods", None)
                    if methods is None:
                        continue

                    model_name = model.name.split("/")[
                        -1
                    ]  # "models/gemini-pro" -> "gemini-pro"

                    # チャット用途（generateContent）かどうかで推奨判定
                    is_recommended = "generateContent" in methods

                    # Vision対応の判定: モデルのメタデータから判定
                    # Gemini APIはinput_token_limitやsupported_modesで判定可能
                    # フォールバック: generateContentがある場合は基本的にVision対応と仮定
                    supports_vision = False
                    if hasattr(model, "supported_modes"):
                        # 新しいAPIではsupported_modesで判定
                        supports_vision = any(
                            "vision" in str(mode).lower()
                            for mode in model.supported_modes
                        )
                    elif "generateContent" in methods:
                        # generateContentがあればマルチモーダル（Vision対応）の可能性が高い
                        # ただし、embedding系は除外
                        supports_vision = "embed" not in model_name.lower()

                    models.append(
                        {
                            "id": f"gemini/{model_name}",
                            "name": model_name,
                            "provider": "Gemini API",
                            "litellm_provider": "gemini",
                            "supports_vision": supports_vision,
                            "supports_json": True,
                            "description": getattr(model, "description", ""),
                            "recommended": is_recommended,
                            "supported_methods": list(methods),  # デバッグ用
                            "cost_per_1k_tokens": {"input": 0.0, "output": 0.0},
                        }
                    )

                # 成功したらループを抜ける
                break

            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = 2**attempt  # 1秒, 2秒, 4秒
                    logger.warning(
                        "⚠️ Retry %d/%d after %ds: %s: %s",
                        attempt + 1,
                        max_retries,
                        wait_time,
                        type(e).__name__,
                        e,
                    )
                    time.sleep(wait_time)
                else:
                    # 最終リトライ失敗
                    logger.error(
                        "❌ Failed after %d attempts: %s: %s",
                        max_retries,
                        type(e).__name__,
                        e,
                    )
                    raise

        if not models:
            logger.warning("No Gemini models found from API")
            return []

        logger.info("✅ Fetched %d Gemini models from API", len(models))

        # キャッシュ保存（1時間TTL）
        _MODEL_CACHE[cache_key] = models
        _CACHE_EXPIRY[cache_key] = datetime.now() + CACHE_TTL

        return models

    except ImportError as e:
        logger.warning("google-genai package not installed: %s", e)
        logger.info("Install with: pip install -U google-genai")
        return []
    except Exception as e:
        logger.error("Failed to fetch Gemini models: %s: %s", type(e).__name__, e)
        return []


def get_openai_models() -> List[Dict[str, Any]]:
    """
    OpenAI APIから実際に利用可能なモデル一覧を動的に取得

    ベストプラクティス対応:
    - APIキーは環境変数から取得（セキュリティ）
    - APIキーがない場合は空リストを返す（優雅な失敗）
    - チャットモデルのみフィルタリング（gpt-, o1-, chatgpt-）
    - キャッシング（1時間TTL）

    Returns:
        モデル情報のリスト（APIキーなしの場合は空リスト）
    """
    cache_key = "openai_models_v1"

    # キャッシュチェック
    if cache_key in _MODEL_CACHE:
        if datetime.now() < _CACHE_EXPIRY.get(cache_key, datetime.min):
            cached_count = len(_MODEL_CACHE[cache_key])
            logger.info("💾 Using cached OpenAI models (%d models)", cached_count)
            return _MODEL_CACHE[cache_key]

    # APIキーチェック（環境変数から取得）
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        logger.info("OPENAI_API_KEY not set, skipping OpenAI models")
        return []

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)

        models_list = []

        # 全モデルを取得
        all_models = client.models.list()

        # チャットモデルのプレフィックス（研究結果に基づく）
        chat_prefixes = ["gpt-", "o1-", "o3-", "o4-", "chatgpt-"]

        for model in all_models:
            # チャット対応モデルのみフィルタ
            if not any(model.id.startswith(prefix) for prefix in chat_prefixes):
                continue

            # Vision対応判定
            supports_vision = any(
                keyword in model.id
                for keyword in ["vision", "gpt-4o", "gpt-4-turbo", "gpt-4.5"]
            )

            # 推奨モデル判定（最新の安定版）
            # 明示的に非推奨のものだけを除外する方式に変更
            # Fine-tunedモデル、古いバージョン、実験的モデルなどを除外
            not_recommended_patterns = [
                "ft:",  # Fine-tunedモデル
                "gpt-4-0613",  # 古いGPT-4スナップショット
                "gpt-4-0314",
                "gpt-3.5-turbo-0301",
                "gpt-3.5-turbo-0613",
                "gpt-3.5-turbo-16k-0613",
                "-preview",  # プレビュー版（o1-previewなど例外あり）
                "gpt-5",  # 未リリースモデル
                "gpt-image",  # 実験的
                "chatgpt-image",  # 実験的
            ]

            # 例外的に推奨するプレビューモデル
            recommended_previews = ["o1-preview", "o1-mini"]

            # 判定：非推奨パターンに該当しないか、または例外リストに含まれる
            is_preview_exception = any(exc in model.id for exc in recommended_previews)
            has_not_recommended_pattern = any(
                pattern in model.id for pattern in not_recommended_patterns
            )

            recommended = (not has_not_recommended_pattern) or is_preview_exception

            # supported_methods推測（OpenAI APIは機能リストを返さないため名前から推測）
            supported_methods = []
            model_id_lower = model.id.lower()

            # Chat/Completions対応
            if any(
                model.id.startswith(p)
                for p in ["gpt-", "o1-", "o3-", "o4-", "chatgpt-"]
            ):
                supported_methods.append("generateContent")

            # Audio対応（transcribe = speech-to-text, tts = text-to-speech）
            if "transcribe" in model_id_lower:
                supported_methods.append("transcribe")
            if "tts" in model_id_lower:
                supported_methods.append("textToSpeech")
            if "audio" in model_id_lower or "realtime" in model_id_lower:
                supported_methods.append("audio")

            # Vision/Multimodal対応
            if supports_vision:
                supported_methods.append("vision")

            models_list.append(
                {
                    "id": f"openai/{model.id}",
                    "name": model.id,
                    "provider": "OpenAI",
                    "litellm_provider": "openai",
                    "supports_vision": supports_vision,
                    "supports_json": True,
                    "recommended": recommended,
                    "supported_methods": supported_methods,
                    "description": f"OpenAI {model.id}",
                    "cost_per_1k_tokens": {"input": 0.0, "output": 0.0},
                }
            )

        # キャッシュ保存
        _MODEL_CACHE[cache_key] = models_list
        _CACHE_EXPIRY[cache_key] = datetime.now() + CACHE_TTL

        logger.info("✅ Found %d OpenAI chat models from API", len(models_list))
        return models_list

    except ImportError as e:
        logger.warning("openai package not installed: %s", e)
        logger.info("Install with: pip install -U openai")
        return []
    except Exception as e:
        logger.warning("OpenAI model discovery failed: %s: %s", type(e).__name__, e)
        return []


def clear_cache():
    """キャッシュをクリア（テスト・デバッグ用）"""
    global _MODEL_CACHE, _CACHE_EXPIRY
    _MODEL_CACHE.clear()
    _CACHE_EXPIRY.clear()
    logger.info("Model cache cleared")
