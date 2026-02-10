"""
Test the fixed image generation function

実APIレスポンス構造を参考にしたモックテスト。
元々はモックなしで実APIを呼ぶデバッグスクリプトだったが、
pytest自動収集時にPydantic警告や未awaitコルーチン警告を引き起こしていたため、
適切なモックテストに書き換え。
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock


async def test_image_gen():
    """Gemini画像生成: 実APIレスポンス構造に基づくモックテスト"""
    from api.llm_client import generate_image_response

    # 実APIレスポンスを忠実に再現したモック
    mock_message = MagicMock()
    mock_message.content = (
        "はい、承知いたしました。"
        "奇妙な背景で逆立ちするファンシーなフェニックスを生成します。\n\n"
    )
    mock_message.images = [
        {"image_url": {"url": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA"}}
    ]

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message = mock_message
    # 実APIの usage 構造を忠実に再現
    mock_response.usage = MagicMock()
    mock_response.usage.model_dump.return_value = {
        "completion_tokens": 1315,
        "prompt_tokens": 15,
        "total_tokens": 1330,
        "completion_tokens_details": {
            "accepted_prediction_tokens": None,
            "audio_tokens": None,
            "reasoning_tokens": None,
            "rejected_prediction_tokens": None,
            "text_tokens": 25,
            "image_tokens": 1290,
        },
        "prompt_tokens_details": {
            "audio_tokens": None,
            "cached_tokens": None,
            "text_tokens": 15,
            "image_tokens": None,
        },
        "cache_read_input_tokens": None,
    }

    with patch("litellm.acompletion", new_callable=AsyncMock) as mock_ac:
        mock_ac.return_value = mock_response
        with patch("litellm.completion_cost", return_value=0.0):
            result = await generate_image_response(
                prompt="ファンシーなフェニックス。",
                model="gemini/gemini-2.5-flash-image",
            )

    assert result["message"]
    assert "フェニックス" in result["message"]
    assert result["image_base64"] == "iVBORw0KGgoAAAANSUhEUgAA"
    assert result["cost"] == 0.0
    assert result["model"] == "gemini/gemini-2.5-flash-image"
    assert "usage" in result
