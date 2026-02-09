"""...LLM Client description..."""

import asyncio
import time
from datetime import datetime
from collections import deque
from typing import Dict, Any
from litellm import acompletion, completion_cost, supports_response_schema
import litellm

from api.config import LITELLM_VERBOSE, LITELLM_TIMEOUT, LITELLM_MAX_RETRIES
from api.logger import setup_logger

logger = setup_logger(__name__)

# LiteLLMの設定
litellm.set_verbose = LITELLM_VERBOSE

# デバッグ用: 直近10件のLLM API通信ログ
llm_api_log = deque(maxlen=10)


def _truncate_for_log(text, max_len=500):
    """ログ用にテキストを制限し、base64画像データをサニタイズ"""
    if not text or not isinstance(text, str):
        return text

    # Base64画像データの検出と置換
    # パターン: data:image/...;base64,<long string>
    import re

    if re.search(r"data:image/[^;]+;base64,", text):
        # base64部分を [base64 image data] に置換
        text = re.sub(
            r"(data:image/[^;]+;base64,)[A-Za-z0-9+/=]+", r"\1[base64 image data]", text
        )

    return text[:max_len] + "..." if len(text) > max_len else text


def _sanitize_messages_for_log(messages):
    """メッセージ配列からログ用に重いデータを省略"""
    if not messages:
        return []
    result = []
    for msg in messages:
        entry = {"role": msg.get("role", "?")}
        content = msg.get("content", "")
        if isinstance(content, str):
            entry["content"] = _truncate_for_log(content)
        elif isinstance(content, list):  # マルチモーダル
            entry["content"] = [
                {"type": p.get("type"), "text": _truncate_for_log(p.get("text", ""))}
                if p.get("type") == "text"
                else {"type": "image_url", "summary": "[Image]"}
                for p in content
            ]
        result.append(entry)
    return result


def _record_llm_log(model, messages, content, usage, cost, duration, attempt, error):
    """LLM API通信をログに記録"""
    llm_api_log.append(
        {
            "timestamp": datetime.now().isoformat(),
            "model": model,
            "messages": _sanitize_messages_for_log(messages),
            "response": _truncate_for_log(content),
            "usage": usage,
            "cost": cost,
            "duration_ms": round(duration * 1000) if duration else None,
            "attempt": attempt + 1,
            "error": error,
        }
    )


async def generate_json(prompt: Any, model: str, retries: int = None) -> Dict[str, Any]:
    """
    LiteLLMを呼び出してJSONレスポンスを生成します。
    リトライロジックとコスト計算が含まれています。

    Args:
        prompt: 以下のいずれかの形式:
               - str: 単純なテキストプロンプト
               - list[dict]: マルチモーダルコンテンツパーツ (例: [{"type": "text", ...}, {"type": "image_url", ...}])
               - list[dict] with 'role' key: 会話履歴を含むメッセージ配列 (例: [{"role": "system", "content": ...}, {"role": "user", "content": ...}])
        model: 使用するモデルID (例: "gemini/gemini-2.0-flash-exp")
        retries: 失敗時の最大リトライ回数 (Noneの場合は設定値を使用)

    Returns:
        {
            "content": str,      # AIが生成したJSON文字列
            "usage": {...},      # トークン使用量統計
            "cost": float,       # 推定コスト (USD)
            "model": str         # 実際に使用されたモデル
        }

    Raises:
        RuntimeError: 全てのリトライが失敗した場合
    """
    if retries is None:
        retries = LITELLM_MAX_RETRIES

    start_time = time.time()
    for attempt in range(retries + 1):
        try:
            # メッセージの準備
            if isinstance(prompt, list):
                # リストの場合: 会話履歴 または マルチモーダルコンテンツ
                if (
                    len(prompt) > 0
                    and isinstance(prompt[0], dict)
                    and "role" in prompt[0]
                ):
                    # 会話履歴形式: [{"role": "system", "content": ...}, {"role": "user", "content": ...}]
                    messages = prompt
                else:
                    # マルチモーダル入力: [{"type": "text", ...}, {"type": "image_url", ...}]
                    messages = [{"role": "user", "content": prompt}]
            else:
                # テキストのみ: 単純な文字列
                messages = [{"role": "user", "content": prompt}]

            # LiteLLM呼び出し (非同期)
            # ベストプラクティス: litellm公式APIでJSONモード対応を事前確認
            # supports_response_schema() は model_cost メタデータより正確
            try:
                model_supports_json = supports_response_schema(
                    model=model, custom_llm_provider=None
                )
            except Exception as e:
                # API確認失敗時はJSONモードを試行（既存の挙動を維持）
                logger.warning("Could not check JSON support for '%s': %s", model, e)
                model_supports_json = True

            extra_kwargs = {}
            if model_supports_json:
                extra_kwargs["response_format"] = {"type": "json_object"}
            else:
                logger.info(
                    "⚠️ Model '%s' does not support JSON mode, using prompt-based JSON guidance",
                    model,
                )

            response = await acompletion(
                model=model,
                messages=messages,
                timeout=LITELLM_TIMEOUT,
                drop_params=True,  # Defense-in-depth: 未サポートパラメータを自動除外
                **extra_kwargs,
            )

            # コンテンツの抽出
            content = response.choices[0].message.content
            if not content:
                raise RuntimeError("Empty AI response")

            # 使用量とコストの計算
            usage = response.usage.model_dump() if hasattr(response, "usage") else {}
            cost = 0.0

            try:
                # LiteLLMの組み込み関数でコストを計算
                cost = completion_cost(completion_response=response)
            except Exception as e:
                logger.warning("Cost calculation failed: %s", e)

            # Thinking/Reasoningコンテンツの抽出（デバッグ用）
            # プロバイダごとに異なる形式で返される
            thinking_content = None
            message = response.choices[0].message

            # Claude: thinking_blocks (list of {type: "thinking", thinking: "..."})
            if hasattr(message, "thinking_blocks") and message.thinking_blocks:
                try:
                    thinking_content = "\n".join(
                        [
                            block.get("thinking", "")
                            if isinstance(block, dict)
                            else str(block)
                            for block in message.thinking_blocks
                        ]
                    )
                except Exception as e:
                    logger.debug("Failed to extract thinking_blocks: %s", e)

            # Gemini/LiteLLM: reasoning_content (string)
            if (
                not thinking_content
                and hasattr(message, "reasoning_content")
                and message.reasoning_content
            ):
                thinking_content = message.reasoning_content

            # OpenAI o1/o3: reasoning_tokensは数値のみ（内容は非公開）
            # usage.completion_tokens_details.reasoning_tokens で確認可能

            # ログ記録（成功時）
            _record_llm_log(
                model,
                messages,
                content,
                usage,
                cost,
                time.time() - start_time,
                attempt,
                None,
            )

            return {
                "content": content,
                "usage": usage,
                "cost": cost,
                "model": model,
                "thinking": thinking_content,  # デバッグ用: None if OpenAI reasoning model
            }

        except Exception as e:
            if attempt == retries:
                # 最大リトライ回数に達した場合はエラーを再送出
                logger.error("Generation failed after %d retries: %s", retries, e)
                # ログ記録（エラー時）
                _record_llm_log(
                    model,
                    messages,
                    None,
                    None,
                    None,
                    time.time() - start_time,
                    attempt,
                    str(e),
                )
                raise RuntimeError(f"AI generation failed: {str(e)}")

            # 指数バックオフ (Exponential Backoff)
            # リトライ間隔を徐々に広げてサーバー負荷を軽減します (2s, 4s, 6s...)
            await asyncio.sleep(2 * (attempt + 1))


def prepare_multimodal_prompt(text: str, image_data: str, image_mime_type: str):
    """
    LiteLLM用のマルチモーダルプロンプトを作成します (OpenAI互換フォーマット)。

    Args:
        text: テキストプロンプト
        image_data: Base64エンコードされた画像データ
        image_mime_type: MIMEタイプ (例: "image/jpeg")

    Returns:
        マルチモーダル入力用のコンテンツリスト
    """
    return [
        {"type": "text", "text": text},
        {
            "type": "image_url",
            "image_url": {"url": f"data:{image_mime_type};base64,{image_data}"},
        },
    ]


async def generate_image_response(prompt: str, model: str) -> Dict[str, Any]:
    """
    画像生成AIを呼び出して画像を生成します。

    Gemini画像生成モデル (completion + modalities) と
    OpenAI DALL-E (image_generation) の両方に対応します。

    Args:
        prompt: 画像生成のためのテキストプロンプト
        model: 使用するモデルID (例: "gemini/gemini-2.5-flash-image", "openai/dall-e-3")

    Returns:
        {
            "message": str,           # AIからのテキストメッセージ (あれば)
            "image_base64": str,      # 生成された画像のbase64データ
            "usage": {...},           # トークン使用量統計
            "cost": float,            # 推定コスト (USD)
            "model": str              # 実際に使用されたモデル
        }

    Raises:
        RuntimeError: 画像生成に失敗した場合
    """
    from litellm import acompletion, aimage_generation, completion_cost

    start_time = time.time()
    provider = model.split("/")[0] if "/" in model else "unknown"

    try:
        # プロバイダー別に適切なAPIパスを選択
        if provider == "gemini":
            # Geminiパス: completion() + modalities
            logger.info(
                "[Image Gen] Using Gemini completion API with modalities for '%s'",
                model,
            )

            response = await acompletion(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                modalities=["image", "text"],
                timeout=LITELLM_TIMEOUT,
                drop_params=True,
            )

            # LiteLLMはGeminiのinlineDataを message.images 配列に変換してくれる
            message = response.choices[0].message
            image_base64 = None
            message_text = ""

            # テキストコンテンツ
            if hasattr(message, "content") and message.content:
                message_text = message.content

            # 画像データの抽出 (LiteLLMが変換した images 配列から)
            if hasattr(message, "images") and message.images:
                for img in message.images:
                    # img is a dictionary with 'image_url' key
                    if isinstance(img, dict) and "image_url" in img:
                        image_url_data = img["image_url"]
                        # image_url_data can be a dict or object
                        url = (
                            image_url_data.get("url")
                            if isinstance(image_url_data, dict)
                            else image_url_data.url
                            if hasattr(image_url_data, "url")
                            else None
                        )
                        # data:image/png;base64,... から base64 部分を抽出
                        if url and url.startswith("data:") and "base64," in url:
                            # Split on "base64," and take everything after it
                            image_base64 = url.split("base64,", 1)[1]
                            break

            # 画像生成成功時にテキストが空の場合のデフォルトメッセージ
            if image_base64 and not message_text:
                message_text = "画像を生成しました"

            if not image_base64:
                # デバッグ用: レスポンス構造をログに出力
                logger.error(
                    "[Image Gen] Response message: content=%s, has_images=%s",
                    message.content,
                    hasattr(message, "images"),
                )
                if hasattr(message, "images"):
                    logger.error("[Image Gen] Images array: %s", message.images)
                raise RuntimeError("No image data found in Gemini response")

        else:
            # 汎用パス: OpenAI DALL-E等
            logger.info("[Image Gen] Using image_generation API for '%s'", model)

            response = await aimage_generation(
                model=model,
                prompt=prompt,
                timeout=LITELLM_TIMEOUT,
            )

            # OpenAI形式のレスポンス
            if not response.data or len(response.data) == 0:
                raise RuntimeError("No image data in response")

            image_data = response.data[0]

            # b64_json または url から画像を取得
            if hasattr(image_data, "b64_json") and image_data.b64_json:
                image_base64 = image_data.b64_json
            elif hasattr(image_data, "url") and image_data.url:
                # URLの場合はダウンロードしてbase64化
                import httpx
                import base64

                async with httpx.AsyncClient() as client:
                    img_response = await client.get(image_data.url)
                    img_response.raise_for_status()
                    image_base64 = base64.b64encode(img_response.content).decode(
                        "utf-8"
                    )
            else:
                raise RuntimeError("No image data (b64_json or url) in response")

            message_text = getattr(image_data, "revised_prompt", "") or prompt

        # 使用量とコスト計算
        usage = response.usage.model_dump() if hasattr(response, "usage") else {}
        cost = 0.0

        try:
            cost = completion_cost(completion_response=response)
        except Exception as e:
            logger.warning("Cost calculation failed for image generation: %s", e)

        duration = time.time() - start_time

        # ログ記録 (base64データはサニタイズされる)
        _record_llm_log(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            content=f"[Image generated] {message_text[:100]}",
            usage=usage,
            cost=cost,
            duration=duration,
            attempt=1,
            error=None,
        )

        logger.info(
            "[Image Gen] Success: model=%s, cost=$%.4f, duration=%.2fs",
            model,
            cost,
            duration,
        )

        return {
            "message": message_text,
            "image_base64": image_base64,
            "usage": usage,
            "cost": cost,
            "model": model,
        }

    except Exception as e:
        duration = time.time() - start_time
        logger.error("[Image Gen] Failed: %s", e)

        _record_llm_log(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            content=None,
            usage={},
            cost=0.0,
            duration=duration,
            attempt=1,
            error=str(e),
        )

        raise RuntimeError(f"Image generation failed: {str(e)}")
