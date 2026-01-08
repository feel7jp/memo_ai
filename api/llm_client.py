"""
LLM Client
LiteLLMを利用してAIプロバイダーとの通信を統一的にハンドリングするクライアントモジュールです。
APIコールの実行、エラーハンドリング、リトライ、コスト計算などの共通処理を実装しています。
"""
import json
import asyncio
from typing import Dict, Any, Optional
from litellm import acompletion, completion_cost
import litellm

from api.config import LITELLM_VERBOSE, LITELLM_TIMEOUT, LITELLM_MAX_RETRIES

# LiteLLMの設定
litellm.set_verbose = LITELLM_VERBOSE


async def generate_json(
    prompt: Any,
    model: str,
    retries: int = None
) -> Dict[str, Any]:
    """
    LiteLLMを呼び出してJSONレスポンスを生成します。
    リトライロジックとコスト計算が含まれています。
    
    Args:
        prompt: テキストプロンプト または マルチモーダルコンテンツのリスト
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
                # マルチモーダル入力: コンテンツパーツのリスト
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
                timeout=LITELLM_TIMEOUT
            )
            
            # コンテンツの抽出
            content = response.choices[0].message.content
            if not content:
                raise RuntimeError("Empty AI response")
            
            # 使用量とコストの計算
            usage = response.usage.dict() if hasattr(response, 'usage') else {}
            cost = 0.0
            
            try:
                # LiteLLMの組み込み関数でコストを計算
                cost = completion_cost(completion_response=response)
            except Exception as e:
                print(f"Cost calculation failed: {e}")
            
            return {
                "content": content,
                "usage": usage,
                "cost": cost,
                "model": model
            }
            
        except Exception as e:
            if attempt == retries:
                # 最大リトライ回数に達した場合はエラーを再送出
                print(f"Generation failed after {retries} retries: {e}")
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
        {"type": "image_url", "image_url": {"url": image_url}}
    ]
