"""
LLM Client
LiteLLMを利用してAIプロバイダーとの通信を統一的にハンドリングするクライアントモジュールです。
APIコールの実行、エラーハンドリング、リトライ、コスト計算などの共通処理を実装しています。
"""

import asyncio
from typing import Dict, Any
from litellm import acompletion, completion_cost
import litellm

from api.config import LITELLM_VERBOSE, LITELLM_TIMEOUT, LITELLM_MAX_RETRIES
from api.logger import setup_logger

logger = setup_logger(__name__)

# LiteLLMの設定
litellm.set_verbose = LITELLM_VERBOSE


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
            # response_format={"type": "json_object"} によりJSON出力を強制します
            response = await acompletion(
                model=model,
                messages=messages,
                response_format={"type": "json_object"},
                timeout=LITELLM_TIMEOUT,
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
                raise RuntimeError(f"AI generation failed: {str(e)}")

            # 指数バックオフ (Exponential Backoff)
            # リトライ間隔を徐々に広げてサーバー負荷を軽減します (2s, 4s, 6s...)
            await asyncio.sleep(2 * (attempt + 1))


def prepare_multimodal_prompt(text: str, image_data: str, image_mime_type: str) -> list:
    """
    LiteLLM用のマルチモーダルプロンプトを作成します (OpenAI互換フォーマット)。

    Args:
        text: テキストプロンプト
        image_data: Base64エンコードされた画像データ
        image_mime_type: MIMEタイプ (例: "image/jpeg")

    Returns:
        マルチモーダル入力用のコンテンツリスト
    """
    image_url = f"data:{image_mime_type};base64,{image_data}"

    return [
        {"type": "text", "text": text},
        {"type": "image_url", "image_url": {"url": image_url}},
    ]
