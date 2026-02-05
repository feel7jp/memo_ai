"""
動的モデル発見モジュール
各プロバイダーAPIから実際に利用可能なモデルを取得し、キャッシュする
"""
import os
from typing import List, Dict, Any
from datetime import datetime, timedelta

# キャッシュ設定
_MODEL_CACHE: Dict[str, List[Dict[str, Any]]] = {}
_CACHE_EXPIRY: Dict[str, datetime] = {}
CACHE_TTL = timedelta(hours=1)


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
            print(f"[INFO] 💾 Using cached Gemini models ({cached_count} models)")
            return _MODEL_CACHE[cache_key]
    
    # Gemini APIから取得（エクスポネンシャルバックオフ）
    try:
        # 新しいパッケージ: google-genai (2024+ recommended)
        import google.genai as genai
        import time
        
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            print("[WARNING] GEMINI_API_KEY not set, using fallback models")
            return _get_fallback_gemini_models()
        
        max_retries = 3
        models = []
        
        for attempt in range(max_retries):
            try:
                # google-genai 新SDK（Client APIを使用）
                client = genai.Client(api_key=api_key)
                
                # client.models.list()でモデル一覧を取得（全モデル）
                for model in client.models.list():
                    if not hasattr(model, 'supported_generation_methods'):
                        continue
                        
                    model_name = model.name.split('/')[-1]  # "models/gemini-pro" -> "gemini-pro"
                    methods = model.supported_generation_methods
                    
                    # チャット用途（generateContent）かどうかで推奨判定
                    is_recommended = 'generateContent' in methods
                    
                    # Vision対応の判定
                    supports_vision = any(pattern in model_name.lower() for pattern in [
                        'flash', 'pro', 'vision', 'image'
                    ])
                    
                    # モデルタイプの判定
                    if 'generateImage' in methods or 'image' in model_name.lower():
                        model_type = "画像生成"
                    elif 'generateAudio' in methods or 'audio' in model_name.lower():
                        model_type = "音声生成"
                    else:
                        model_type = "チャット"
                    
                    models.append({
                        "id": f"gemini/{model_name}",
                        "name": model_name,
                        "provider": "Gemini API",
                        "litellm_provider": "gemini",
                        "supports_vision": supports_vision,
                        "supports_json": True,
                        "description": getattr(model, 'description', ''),
                        "recommended": is_recommended,  # 推奨フラグ（チャット用途）
                        "model_type": model_type,  # モデルタイプ
                        "supported_methods": list(methods),  # デバッグ用
                        "cost_per_1k_tokens": {
                            "input": 0.0,
                            "output": 0.0
                        }
                    })
                
                # 成功したらループを抜ける
                break
                
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # 1秒, 2秒, 4秒
                    print(f"[WARNING] ⚠️ Retry {attempt + 1}/{max_retries} after {wait_time}s: {type(e).__name__}: {e}")
                    time.sleep(wait_time)
                else:
                    # 最終リトライ失敗
                    print(f"[ERROR] ❌ Failed after {max_retries} attempts: {type(e).__name__}: {e}")
                    raise
        
        if not models:
            print("[WARNING] No Gemini models found, using fallback")
            return _get_fallback_gemini_models()
        
        print(f"[INFO] ✅ Fetched {len(models)} Gemini models from API")
        
        # 教育用：APIから取得できた場合でも、他の種類のモデル（画像・埋め込みなど）も
        # 「非推奨」として表示するためにリストに追加する
        educational_examples = [
            {
                "id": "gemini/imagen-3.0-generate-001",
                "name": "imagen-3.0-generate-001",
                "provider": "Gemini API",
                "litellm_provider": "gemini",
                "supports_vision": False,
                "supports_json": False,
                "description": "Imagen 3 (Image Generation)",
                "recommended": False,
                "model_type": "画像生成",
                "cost_per_1k_tokens": {"input": 0.0, "output": 0.0}
            },
            {
                "id": "gemini/text-embedding-004",
                "name": "text-embedding-004",
                "provider": "Gemini API",
                "litellm_provider": "gemini",
                "supports_vision": False,
                "supports_json": True,
                "description": "Text Embedding Model",
                "recommended": False,
                "model_type": "埋め込み",
                "cost_per_1k_tokens": {"input": 0.0, "output": 0.0}
            },
            {
                "id": "gemini/aqa",
                "name": "aqa",
                "provider": "Gemini API",
                "litellm_provider": "gemini",
                "supports_vision": False,
                "supports_json": True,
                "description": "Attributed Question Answering",
                "recommended": False,
                "model_type": "Q&A",
                "cost_per_1k_tokens": {"input": 0.0, "output": 0.0}
            }
        ]
        
        # IDで重複チェックしつつマージ
        existing_ids = {m["id"] for m in models}
        for ex in educational_examples:
            if ex["id"] not in existing_ids:
                models.append(ex)
        
        # キャッシュ保存（1時間TTL）
        _MODEL_CACHE[cache_key] = models
        _CACHE_EXPIRY[cache_key] = datetime.now() + CACHE_TTL
        
        return models
        
    except ImportError as e:
        print(f"[WARNING] google-genai package not installed: {e}")
        print("[INFO] Install with: pip install -U google-genai")
        return _get_fallback_gemini_models()
    except Exception as e:
        print(f"[ERROR] Failed to fetch Gemini models: {type(e).__name__}: {e}")
        return _get_fallback_gemini_models()


def _get_fallback_gemini_models() -> List[Dict[str, Any]]:
    """
    フォールバック: APIエラー時の最小限の推奨モデル + 教育用非推奨モデル
    """
    return [
        # --- 推奨モデル (Chat) ---
        {
            "id": "gemini/gemini-flash-latest",
            "name": "gemini-flash-latest",
            "provider": "Gemini API",
            "litellm_provider": "gemini",
            "supports_vision": True,
            "supports_json": True,
            "description": "Latest Gemini Flash model",
            "recommended": True,
            "model_type": "チャット",
            "cost_per_1k_tokens": {"input": 0.0, "output": 0.0}
        },
        {
            "id": "gemini/gemini-pro-latest",
            "name": "gemini-pro-latest",
            "provider": "Gemini API",
            "litellm_provider": "gemini",
            "supports_vision": True,
            "supports_json": True,
            "description": "Latest Gemini Pro model",
            "recommended": True,
            "model_type": "チャット",
            "cost_per_1k_tokens": {"input": 0.0, "output": 0.0}
        },
        {
            "id": "gemini/gemini-2.5-flash",
            "name": "gemini-2.5-flash",
            "provider": "Gemini API",
            "litellm_provider": "gemini",
            "supports_vision": True,
            "supports_json": True,
            "description": "Gemini 2.5 Flash",
            "recommended": True,
            "model_type": "チャット",
            "cost_per_1k_tokens": {"input": 0.0, "output": 0.0}
        },
        {
            "id": "gemini/gemini-2.5-pro",
            "name": "gemini-2.5-pro",
            "provider": "Gemini API",
            "litellm_provider": "gemini",
            "supports_vision": True,
            "supports_json": True,
            "description": "Gemini 2.5 Pro",
            "recommended": True,
            "model_type": "チャット",
            "cost_per_1k_tokens": {"input": 0.0, "output": 0.0}
        },
        # --- 非推奨モデル (Examples) ---
        {
            "id": "gemini/imagen-3.0-generate-001",
            "name": "imagen-3.0-generate-001",
            "provider": "Gemini API",
            "litellm_provider": "gemini",
            "supports_vision": False,
            "supports_json": False,
            "description": "Imagen 3 (Image Generation)",
            "recommended": False,
            "model_type": "画像生成",
            "cost_per_1k_tokens": {"input": 0.0, "output": 0.0}
        },
        {
            "id": "gemini/text-embedding-004",
            "name": "text-embedding-004",
            "provider": "Gemini API",
            "litellm_provider": "gemini",
            "supports_vision": False,
            "supports_json": True,
            "description": "Text Embedding Model",
            "recommended": False,
            "model_type": "埋め込み",
            "cost_per_1k_tokens": {"input": 0.0, "output": 0.0}
        }
    ]


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
            print(f"[INFO] 💾 Using cached OpenAI models ({cached_count} models)")
            return _MODEL_CACHE[cache_key]
    
    # APIキーチェック（環境変数から取得）
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("[INFO] OPENAI_API_KEY not set, skipping OpenAI models")
        return []
    
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        
        models_list = []
        
        # 全モデルを取得
        all_models = client.models.list()
        
        # チャットモデルのプレフィックス（研究結果に基づく）
        chat_prefixes = ['gpt-', 'o1-', 'o3-', 'o4-', 'chatgpt-']
        
        for model in all_models:
            # チャット対応モデルのみフィルタ
            if not any(model.id.startswith(prefix) for prefix in chat_prefixes):
                continue
            
            # Vision対応判定
            supports_vision = any(keyword in model.id for keyword in [
                'vision', 'gpt-4o', 'gpt-4-turbo', 'gpt-4.5'
            ])
            
            # 推奨モデル判定（最新の安定版）
            # 明示的に非推奨のものだけを除外する方式に変更
            # Fine-tunedモデル、古いバージョン、実験的モデルなどを除外
            not_recommended_patterns = [
                'ft:',              # Fine-tunedモデル
                'gpt-4-0613',       # 古いGPT-4スナップショット
                'gpt-4-0314',
                'gpt-3.5-turbo-0301',
                'gpt-3.5-turbo-0613',
                'gpt-3.5-turbo-16k-0613',
                '-preview',         # プレビュー版（o1-previewなど例外あり）
                'gpt-5',            # 未リリースモデル
                'gpt-image',        # 実験的
                'chatgpt-image',    # 実験的
            ]
            
            # 例外的に推奨するプレビューモデル
            recommended_previews = ['o1-preview', 'o1-mini']
            
            # 判定：非推奨パターンに該当しないか、または例外リストに含まれる
            is_preview_exception = any(exc in model.id for exc in recommended_previews)
            has_not_recommended_pattern = any(pattern in model.id for pattern in not_recommended_patterns)
            
            recommended = (not has_not_recommended_pattern) or is_preview_exception
            
            models_list.append({
                "id": f"openai/{model.id}",
                "name": model.id,
                "provider": "OpenAI",
                "litellm_provider": "openai",
                "supports_vision": supports_vision,
                "supports_json": True,
                "recommended": recommended,
                "model_type": "チャット",
                "description": f"OpenAI {model.id}",
                "cost_per_1k_tokens": {"input": 0.0, "output": 0.0}
            })
        
        # キャッシュ保存
        _MODEL_CACHE[cache_key] = models_list
        _CACHE_EXPIRY[cache_key] = datetime.now() + CACHE_TTL
        
        print(f"[INFO] ✅ Found {len(models_list)} OpenAI chat models from API")
        return models_list
        
    except ImportError as e:
        print(f"[WARNING] openai package not installed: {e}")
        print("[INFO] Install with: pip install -U openai")
        return []
    except Exception as e:
        print(f"[WARNING] OpenAI model discovery failed: {type(e).__name__}: {e}")
        return []


def clear_cache():
    """キャッシュをクリア（テスト・デバッグ用）"""
    global _MODEL_CACHE, _CACHE_EXPIRY
    _MODEL_CACHE.clear()
    _CACHE_EXPIRY.clear()
    print("[INFO] Model cache cleared")
